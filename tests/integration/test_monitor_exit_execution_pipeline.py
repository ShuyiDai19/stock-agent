import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.errors import (
    RobinhoodOrderReviewRejectedError,
)
from stock_agent.brokers.robinhood.exit_executor import (
    DryRunRobinhoodExitExecutor,
    LiveRobinhoodExitExecutor,
)
from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
)
from stock_agent.brokers.robinhood.pricing import (
    RobinhoodExitPriceQuote,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)
from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionStatus,
    ExitExecutionService,
)
from stock_agent.monitoring.trailing_stop_monitor import (
    TrailingStopMonitor,
)
from stock_agent.orchestration.exit_execution import (
    ExitExecutionCoordinator,
)
from stock_agent.risk import TrailingStopDecision
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)


class SequencedFakeMCPInvoker:
    def __init__(self, payloads) -> None:
        self._payloads = list(payloads)
        self.calls = []

    def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments)))

        if not self._payloads:
            raise AssertionError("unexpected extra MCP call")

        return self._payloads.pop(0)


def make_quote_payload(*, bid: str, observed_at: str) -> dict:
    return {
        "data": {
            "results": [
                {
                    "quote": {
                        "symbol": "AAPL",
                        "last_trade_price": bid,
                        "venue_last_trade_time": observed_at,
                        "bid_price": bid,
                        "venue_bid_time": observed_at,
                        "ask_price": bid,
                        "venue_ask_time": observed_at,
                        "has_traded": True,
                        "state": "active",
                    }
                }
            ]
        }
    }


_INITIAL_TIME = datetime(
    2026,
    9,
    17,
    20,
    0,
    0,
    tzinfo=timezone.utc,
)


def make_position_state() -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id="position-1",
        account_number="agentic-account",
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        opening_order_id="opening-order-1",
        entry_price=Decimal("100"),
        remaining_quantity=Decimal("1"),
        opened_at=_INITIAL_TIME,
        highest_executable_bid=Decimal("105"),
        trailing_armed=True,
        trailing_armed_at=_INITIAL_TIME,
        activation_gain_ratio=Decimal("0.04"),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_INITIAL_TIME,
        last_reconciled_at=_INITIAL_TIME,
        status=PositionStateStatus.ACTIVE,
    )


class FakeExitPriceProvider:
    def __init__(
        self,
        *,
        executable_bid: Decimal,
        observed_at: datetime,
    ) -> None:
        self._executable_bid = executable_bid
        self._observed_at = observed_at
        self.requests = []

    def get_exit_price(self, request) -> RobinhoodExitPriceQuote:
        self.requests.append(request)

        return RobinhoodExitPriceQuote(
            symbol=request.symbol,
            executable_bid=self._executable_bid,
            observed_at=self._observed_at,
            option_id=request.option_id,
        )


@dataclass(frozen=True)
class FakeOrderReview:
    submission: RobinhoodExitSubmission
    approved: bool


@dataclass(frozen=True)
class FakeOrderReceipt:
    broker_order_id: str
    submitted_at: datetime


class FakeRobinhoodBrokerClient:
    def __init__(
        self,
        *,
        approved: bool = True,
        submitted_at: datetime,
    ) -> None:
        self.approved = approved
        self.submitted_at = submitted_at
        self.reviewed = []
        self.submitted = []

    def review_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> FakeOrderReview:
        self.reviewed.append(submission)

        return FakeOrderReview(
            submission=submission,
            approved=self.approved,
        )

    def submit_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> FakeOrderReceipt:
        self.submitted.append(submission)

        return FakeOrderReceipt(
            broker_order_id="broker-order-123",
            submitted_at=self.submitted_at,
        )


class MonitorExitExecutionPipelineTests(unittest.TestCase):
    def test_exit_monitor_outcome_is_previewed_by_dry_run_executor(
        self,
    ) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="102.90",
                    observed_at="2026-09-17T20:01:00Z",
                )
            ]
        )
        quote_provider = MCPRobinhoodEquityQuoteProvider(invoker)

        fixed_execution_time = datetime(
            2026,
            9,
            17,
            20,
            1,
            1,
            tzinfo=timezone.utc,
        )

        executor = DryRunRobinhoodExitExecutor(
            clock=lambda: fixed_execution_time
        )
        execution_service = ExitExecutionService(executor)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory) / "positions.sqlite3"
            )
            store.initialize()

            coordinator = ExitExecutionCoordinator(
                execution_service,
                store,
            )

            state = make_position_state()
            store.insert(state)

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            monitor_outcomes = monitor.monitor_active_positions(
                account_number="agentic-account"
            )

            self.assertEqual(len(monitor_outcomes), 1)

            monitor_outcome = monitor_outcomes[0]
            self.assertTrue(monitor_outcome.succeeded)
            self.assertEqual(
                monitor_outcome.evaluation.decision,
                TrailingStopDecision.EXIT,
            )
            self.assertIsNotNone(monitor_outcome.exit_intent)

            execution_outcomes = coordinator.execute_outcomes(
                monitor_outcomes
            )

            self.assertEqual(len(execution_outcomes), 1)

            execution_outcome = execution_outcomes[0]
            self.assertIsNone(execution_outcome.error)
            self.assertIsNotNone(execution_outcome.result)
            self.assertEqual(
                execution_outcome.result.status,
                ExecutionStatus.PREVIEWED,
            )

            self.assertIsNotNone(executor.last_request)
            self.assertEqual(executor.last_request.symbol, "AAPL")
            self.assertEqual(
                executor.last_request.quantity,
                Decimal("1"),
            )

            persisted = store.get(state.position_id)
            self.assertEqual(
                persisted.status,
                PositionStateStatus.ACTIVE,
            )

    def test_hold_outcome_does_not_execute(self) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="104.00",
                    observed_at="2026-09-17T20:01:00Z",
                )
            ]
        )
        quote_provider = MCPRobinhoodEquityQuoteProvider(invoker)
        executor = DryRunRobinhoodExitExecutor()
        execution_service = ExitExecutionService(executor)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory) / "positions.sqlite3"
            )
            store.initialize()

            coordinator = ExitExecutionCoordinator(
                execution_service,
                store,
            )

            state = make_position_state()
            store.insert(state)

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            monitor_outcomes = monitor.monitor_active_positions(
                account_number="agentic-account"
            )

            self.assertEqual(
                monitor_outcomes[0].evaluation.decision,
                TrailingStopDecision.HOLD,
            )
            self.assertIsNone(monitor_outcomes[0].exit_intent)

            execution_outcomes = coordinator.execute_outcomes(
                monitor_outcomes
            )

            self.assertIsNone(execution_outcomes[0].result)
            self.assertIsNone(executor.last_request)

    def test_monitor_error_does_not_execute(self) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="102.90",
                    observed_at="2026-09-17T19:59:00Z",
                )
            ]
        )
        quote_provider = MCPRobinhoodEquityQuoteProvider(invoker)
        executor = DryRunRobinhoodExitExecutor()
        execution_service = ExitExecutionService(executor)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory) / "positions.sqlite3"
            )
            store.initialize()

            coordinator = ExitExecutionCoordinator(
                execution_service,
                store,
            )

            state = make_position_state()
            store.insert(state)

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            monitor_outcomes = monitor.monitor_active_positions(
                account_number="agentic-account"
            )

            self.assertFalse(monitor_outcomes[0].succeeded)

            execution_outcomes = coordinator.execute_outcomes(
                monitor_outcomes
            )

            self.assertIsNone(execution_outcomes[0].result)
            self.assertIsNone(executor.last_request)

    def test_exit_flows_through_live_executor_to_submitted(
        self,
    ) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="102.90",
                    observed_at="2026-09-17T20:01:00Z",
                )
            ]
        )
        quote_provider = MCPRobinhoodEquityQuoteProvider(invoker)

        exit_price_provider = FakeExitPriceProvider(
            executable_bid=Decimal("102.85"),
            observed_at=datetime(
                2026,
                9,
                17,
                20,
                1,
                1,
                tzinfo=timezone.utc,
            ),
        )

        broker = FakeRobinhoodBrokerClient(
            approved=True,
            submitted_at=datetime(
                2026,
                9,
                17,
                20,
                1,
                2,
                tzinfo=timezone.utc,
            ),
        )

        executor = LiveRobinhoodExitExecutor(
            client=broker,
            price_provider=exit_price_provider,
            ref_id_factory=lambda: "00000000-0000-4000-8000-000000000001",
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory) / "positions.sqlite3"
            )
            store.initialize()

            state = make_position_state()
            store.insert(state)

            coordinator = ExitExecutionCoordinator(
                ExitExecutionService(executor),
                store,
            )

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            monitor_outcomes = monitor.monitor_active_positions(
                account_number="agentic-account"
            )

            self.assertEqual(
                monitor_outcomes[0].evaluation.decision,
                TrailingStopDecision.EXIT,
            )
            self.assertIsNotNone(monitor_outcomes[0].exit_intent)

            execution_outcomes = coordinator.execute_outcomes(
                monitor_outcomes
            )

            self.assertEqual(len(execution_outcomes), 1)

            execution_outcome = execution_outcomes[0]
            self.assertIsNone(execution_outcome.error)
            self.assertIsNotNone(execution_outcome.result)
            self.assertEqual(
                execution_outcome.result.status,
                ExecutionStatus.SUBMITTED,
            )
            self.assertEqual(
                execution_outcome.result.broker_order_id,
                "broker-order-123",
            )

            self.assertEqual(len(exit_price_provider.requests), 1)
            self.assertEqual(len(broker.reviewed), 1)
            self.assertEqual(len(broker.submitted), 1)
            self.assertEqual(
                broker.reviewed[0],
                broker.submitted[0],
            )
            self.assertEqual(
                broker.submitted[0].ref_id,
                "00000000-0000-4000-8000-000000000001",
            )

            persisted = store.get(state.position_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(
                persisted.status,
                PositionStateStatus.CLOSING,
            )
            self.assertEqual(
                persisted.version,
                state.version + 2,
            )

    def test_rejected_review_never_submits_order(
        self,
    ) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="102.90",
                    observed_at="2026-09-17T20:01:00Z",
                )
            ]
        )
        quote_provider = MCPRobinhoodEquityQuoteProvider(invoker)

        exit_price_provider = FakeExitPriceProvider(
            executable_bid=Decimal("102.85"),
            observed_at=datetime(
                2026,
                9,
                17,
                20,
                1,
                1,
                tzinfo=timezone.utc,
            ),
        )

        broker = FakeRobinhoodBrokerClient(
            approved=False,
            submitted_at=datetime(
                2026,
                9,
                17,
                20,
                1,
                2,
                tzinfo=timezone.utc,
            ),
        )

        executor = LiveRobinhoodExitExecutor(
            client=broker,
            price_provider=exit_price_provider,
            ref_id_factory=lambda: "00000000-0000-4000-8000-000000000002",
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory) / "positions.sqlite3"
            )
            store.initialize()

            state = make_position_state()
            store.insert(state)

            coordinator = ExitExecutionCoordinator(
                ExitExecutionService(executor),
                store,
            )

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            monitor_outcomes = monitor.monitor_active_positions(
                account_number="agentic-account"
            )

            execution_outcomes = coordinator.execute_outcomes(
                monitor_outcomes
            )
            execution_outcome = execution_outcomes[0]

            self.assertIsNone(execution_outcome.result)
            self.assertIsInstance(
                execution_outcome.error,
                RobinhoodOrderReviewRejectedError,
            )
            self.assertEqual(len(broker.reviewed), 1)
            self.assertEqual(broker.submitted, [])

            persisted = store.get(state.position_id)
            self.assertEqual(
                persisted.status,
                PositionStateStatus.ACTIVE,
            )


if __name__ == "__main__":
    unittest.main()