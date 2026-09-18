import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
)
from stock_agent.domain import AssetType
from stock_agent.monitoring.trailing_stop_monitor import (
    TrailingStopMonitor,
)
from stock_agent.risk import (
    TrailingStopDecision,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)


class SequencedFakeMCPInvoker:
    def __init__(
        self,
        payloads,
    ) -> None:
        self._payloads = list(payloads)
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        if not self._payloads:
            raise AssertionError(
                "unexpected extra MCP call"
            )

        return self._payloads.pop(0)


def make_quote_payload(
    *,
    bid: str,
    observed_at: str,
) -> dict:
    return {
        "data": {
            "results": [
                {
                    "quote": {
                        "symbol": "AAPL",
                        "last_trade_price": bid,
                        "venue_last_trade_time":
                            observed_at,
                        "bid_price": bid,
                        "venue_bid_time":
                            observed_at,
                        "ask_price": bid,
                        "venue_ask_time":
                            observed_at,
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
    19,
    59,
    0,
    tzinfo=timezone.utc,
)


def make_position_state(
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id="position-1",
        account_number="agentic-account",
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        opening_order_id="opening-order-1",
        entry_price=Decimal("100"),
        remaining_quantity=Decimal("1"),
        opened_at=_INITIAL_TIME,
        highest_executable_bid=Decimal("100"),
        trailing_armed=False,
        trailing_armed_at=None,
        activation_gain_ratio=Decimal("0.04"),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_INITIAL_TIME,
        last_reconciled_at=_INITIAL_TIME,
        status=PositionStateStatus.ACTIVE,
    )

class RobinhoodTrailingMonitorIntegrationTests(
    unittest.TestCase
):
    def test_real_quote_provider_drives_full_trailing_lifecycle(
        self,
    ) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="103.00",
                    observed_at=(
                        "2026-09-17T20:00:00Z"
                    ),
                ),
                make_quote_payload(
                    bid="104.00",
                    observed_at=(
                        "2026-09-17T20:01:00Z"
                    ),
                ),
                make_quote_payload(
                    bid="105.00",
                    observed_at=(
                        "2026-09-17T20:02:00Z"
                    ),
                ),
                make_quote_payload(
                    bid="102.90",
                    observed_at=(
                        "2026-09-17T20:03:00Z"
                    ),
                ),
            ]
        )

        quote_provider = (
            MCPRobinhoodEquityQuoteProvider(
                invoker
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory)
                / "positions.sqlite3"
            )
            store.initialize()

            initial_state = (
                make_position_state()
            )
            store.insert(
                initial_state
            )

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            first = monitor.process_position(
                initial_state.position_id
            )

            self.assertEqual(
                first.decision,
                TrailingStopDecision.HOLD,
            )

            self.assertEqual(
                first.state
                .highest_executable_bid,
                Decimal("103.00"),
            )

            self.assertFalse(
                first.state.trailing_armed
            )

            second = monitor.process_position(
                initial_state.position_id
            )

            self.assertEqual(
                second.decision,
                TrailingStopDecision.HOLD,
            )

            self.assertTrue(
                second.state.trailing_armed
            )

            self.assertEqual(
                second.state
                .highest_executable_bid,
                Decimal("104.00"),
            )

            third = monitor.process_position(
                initial_state.position_id
            )

            self.assertEqual(
                third.decision,
                TrailingStopDecision.HOLD,
            )

            self.assertEqual(
                third.state
                .highest_executable_bid,
                Decimal("105.00"),
            )

            fourth = monitor.process_position(
                initial_state.position_id
            )

            self.assertEqual(
                fourth.decision,
                TrailingStopDecision.EXIT,
            )

            self.assertEqual(
                fourth.state
                .highest_executable_bid,
                Decimal("105.00"),
            )

            persisted = store.get(
                initial_state.position_id
            )

            self.assertIsNotNone(
                persisted
            )

            self.assertEqual(
                persisted.status,
                PositionStateStatus.ACTIVE,
            )

            self.assertTrue(
                persisted.trailing_armed
            )

            self.assertEqual(
                persisted
                .highest_executable_bid,
                Decimal("105.00"),
            )

            self.assertEqual(
                persisted.last_quote_at,
                datetime(
                    2026,
                    9,
                    17,
                    20,
                    3,
                    0,
                    tzinfo=timezone.utc,
                ),
            )

            self.assertEqual(
                persisted.version,
                initial_state.version + 4,
            )

            self.assertEqual(
                invoker.calls,
                [
                    (
                        "get_equity_quotes",
                        {
                            "symbols": [
                                "AAPL",
                            ],
                        },
                    ),
                    (
                        "get_equity_quotes",
                        {
                            "symbols": [
                                "AAPL",
                            ],
                        },
                    ),
                    (
                        "get_equity_quotes",
                        {
                            "symbols": [
                                "AAPL",
                            ],
                        },
                    ),
                    (
                        "get_equity_quotes",
                        {
                            "symbols": [
                                "AAPL",
                            ],
                        },
                    ),
                ],
            )

    def test_exit_evaluation_produces_exit_intent(
        self,
    ) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                make_quote_payload(
                    bid="102.90",
                    observed_at=(
                        "2026-09-17T20:03:00Z"
                    ),
                )
            ]
        )

        quote_provider = (
            MCPRobinhoodEquityQuoteProvider(
                invoker
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory)
                / "positions.sqlite3"
            )
            store.initialize()

            state = make_position_state()

            from dataclasses import replace

            armed_state = replace(
                state,
                highest_executable_bid=(
                    Decimal("105")
                ),
                trailing_armed=True,
                trailing_armed_at=datetime(
                    2026,
                    9,
                    17,
                    20,
                    1,
                    0,
                    tzinfo=timezone.utc,
                ),
                last_quote_at=datetime(
                    2026,
                    9,
                    17,
                    20,
                    2,
                    0,
                    tzinfo=timezone.utc,
                ),
            )

            store.insert(
                armed_state
            )

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            outcomes = (
                monitor.monitor_active_positions(
                    account_number=(
                        "agentic-account"
                    )
                )
            )

            self.assertEqual(
                len(outcomes),
                1,
            )

            outcome = outcomes[0]

            self.assertTrue(
                outcome.succeeded
            )

            self.assertEqual(
                outcome.evaluation.decision,
                TrailingStopDecision.EXIT,
            )

            self.assertIsNotNone(
                outcome.exit_intent
            )

            persisted = store.get(
                state.position_id
            )

            self.assertEqual(
                persisted.status,
                PositionStateStatus.ACTIVE,
            )