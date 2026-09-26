import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExitIntent,
    ExitReason,
)
from stock_agent.monitoring import (
    PositionMonitorOutcome,
)
from stock_agent.orchestration.robinhood_equity_exit_cycle import (
    RobinhoodEquityExitCycleError,
    RobinhoodEquityExitCycleStatus,
    run_robinhood_equity_exit_cycle,
)
from stock_agent.risk import (
    TrailingStopDecision,
    TrailingStopEvaluation,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


_NOW = datetime(
    2026,
    9,
    25,
    20,
    0,
    tzinfo=timezone.utc,
)


def make_active_state(
    *,
    position_id: str = "position-1",
    symbol: str = "AAPL",
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id=position_id,
        account_number=(
            "agentic-account"
        ),
        asset_type=AssetType.EQUITY,
        symbol=symbol,
        opening_order_id=(
            f"opening-{position_id}"
        ),
        entry_price=Decimal("100"),
        remaining_quantity=(
            Decimal("1")
        ),
        opened_at=_NOW,
        highest_executable_bid=(
            Decimal("105")
        ),
        trailing_armed=True,
        trailing_armed_at=_NOW,
        activation_gain_ratio=(
            Decimal("0.04")
        ),
        drawdown_ratio=(
            Decimal("0.02")
        ),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
        status=(
            PositionStateStatus.ACTIVE
        ),
    )


def make_exit_intent(
    *,
    position_id: str = "position-1",
    symbol: str = "AAPL",
) -> ExitIntent:
    state = make_active_state(
        position_id=position_id,
        symbol=symbol,
    )

    return ExitIntent(
        position_id=state.position_id,
        account_number=(
            state.account_number
        ),
        asset_type=state.asset_type,
        symbol=state.symbol,
        quantity=(
            state.remaining_quantity
        ),
        reason=(
            ExitReason.TRAILING_STOP
        ),
        triggered_at=(
            state.last_quote_at
        ),
        option_id=state.option_id,
    )


def make_actionable_outcome(
    *,
    position_id: str = "position-1",
    symbol: str = "AAPL",
) -> PositionMonitorOutcome:
    state = make_active_state(
        position_id=position_id,
        symbol=symbol,
    )

    evaluation = (
        TrailingStopEvaluation(
            state=state,
            decision=(
                TrailingStopDecision.EXIT
            ),
            reason=(
                "trailing stop triggered"
            ),
        )
    )

    intent = ExitIntent(
        position_id=state.position_id,
        account_number=(
            state.account_number
        ),
        asset_type=state.asset_type,
        symbol=state.symbol,
        quantity=(
            state.remaining_quantity
        ),
        reason=(
            ExitReason.TRAILING_STOP
        ),
        triggered_at=(
            state.last_quote_at
        ),
        option_id=state.option_id,
    )

    return PositionMonitorOutcome(
        position_id=state.position_id,
        symbol=state.symbol,
        evaluation=evaluation,
        exit_intent=intent,
    )


class FakeReconciler:
    def __init__(
        self,
        events,
        *,
        error=None,
    ) -> None:
        self.events = events
        self.error = error

    def reconcile(
        self,
        *,
        account_number,
    ):
        self.events.append(
            "reconcile"
        )

        if self.error is not None:
            raise self.error

        return ()


class FakeMonitor:
    def __init__(
        self,
        events,
        outcomes,
    ) -> None:
        self.events = events
        self.outcomes = outcomes

    def monitor_active_positions(
        self,
        *,
        account_number,
    ):
        self.events.append(
            "monitor"
        )

        return list(
            self.outcomes
        )


class FakeCoordinator:
    def __init__(
        self,
        events,
        *,
        result=None,
        error=None,
    ) -> None:
        self.events = events
        self.result = result
        self.error = error
        self.calls = []

    def execute_outcome(
        self,
        outcome,
    ):
        self.events.append(
            "execute"
        )

        self.calls.append(
            outcome
        )

        if self.error is not None:
            raise self.error

        return self.result


class RobinhoodEquityExitCycleTests(
    unittest.TestCase
):
    def test_reconciles_before_monitoring(
        self,
    ) -> None:
        events = []

        result = (
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [],
                    )
                ),
                execution_coordinator=(
                    FakeCoordinator(
                        events
                    )
                ),
            )
        )

        self.assertEqual(
            events,
            [
                "reconcile",
                "monitor",
            ],
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityExitCycleStatus
            .NO_ACTION,
        )

    def test_reconciliation_failure_stops_cycle(
        self,
    ) -> None:
        events = []

        with self.assertRaisesRegex(
            RuntimeError,
            "closing order unresolved",
        ):
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events,
                        error=RuntimeError(
                            "closing order unresolved"
                        ),
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [],
                    )
                ),
                execution_coordinator=(
                    FakeCoordinator(
                        events
                    )
                ),
            )

        self.assertEqual(
            events,
            [
                "reconcile",
            ],
        )

    def test_monitor_failure_blocks_all_execution(
        self,
    ) -> None:
        events = []

        failed = (
            PositionMonitorOutcome(
                position_id=(
                    "position-1"
                ),
                symbol="AAPL",
                error=RuntimeError(
                    "quote unavailable"
                ),
            )
        )

        coordinator = (
            FakeCoordinator(
                events,
                result=None,
            )
        )

        with self.assertRaisesRegex(
            RobinhoodEquityExitCycleError,
            "monitoring failed",
        ):
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [
                            failed,
                        ],
                    )
                ),
                execution_coordinator=(
                    coordinator
                ),
            )

        self.assertEqual(
            coordinator.calls,
            [],
        )

        self.assertEqual(
            events,
            [
                "reconcile",
                "monitor",
            ],
        )

    def test_multiple_exit_intents_fail_before_execution(
        self,
    ) -> None:
        events = []

        coordinator = (
            FakeCoordinator(
                events
            )
        )

        outcomes = [
            make_actionable_outcome(
                position_id="position-aapl",
                symbol="AAPL",
            ),
            make_actionable_outcome(
                position_id="position-msft",
                symbol="MSFT",
            ),
        ]

        with self.assertRaisesRegex(
            RobinhoodEquityExitCycleError,
            "multiple equity exit intents",
        ):
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        outcomes,
                    )
                ),
                execution_coordinator=(
                    coordinator
                ),
            )

        self.assertEqual(
            coordinator.calls,
            [],
        )

    def test_single_previewed_exit_is_returned(
        self,
    ) -> None:
        events = []

        execution_result = (
            ExecutionResult(
                position_id="position-1",
                status=(
                    ExecutionStatus
                    .PREVIEWED
                ),
                submitted_at=_NOW,
            )
        )

        result = (
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [
                            make_actionable_outcome()
                        ],
                    )
                ),
                execution_coordinator=(
                    FakeCoordinator(
                        events,
                        result=(
                            execution_result
                        ),
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityExitCycleStatus
            .PREVIEWED,
        )

        self.assertFalse(
            result.order_submitted
        )

        self.assertEqual(
            events,
            [
                "reconcile",
                "monitor",
                "execute",
            ],
        )

    def test_single_submitted_exit_is_returned(
        self,
    ) -> None:
        events = []

        execution_result = (
            ExecutionResult(
                position_id="position-1",
                status=(
                    ExecutionStatus
                    .SUBMITTED
                ),
                submitted_at=_NOW,
                broker_order_id=(
                    "broker-order-1"
                ),
            )
        )

        result = (
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [
                            make_actionable_outcome()
                        ],
                    )
                ),
                execution_coordinator=(
                    FakeCoordinator(
                        events,
                        result=(
                            execution_result
                        ),
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityExitCycleStatus
            .SUBMITTED,
        )

        self.assertTrue(
            result.order_submitted
        )

        self.assertEqual(
            result.execution_result,
            execution_result,
        )

    def test_execution_failure_propagates(
        self,
    ) -> None:
        events = []

        with self.assertRaisesRegex(
            RuntimeError,
            "submission failed",
        ):
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(
                        events
                    )
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [
                            make_actionable_outcome()
                        ],
                    )
                ),
                execution_coordinator=(
                    FakeCoordinator(
                        events,
                        error=RuntimeError(
                            "submission failed"
                        ),
                    )
                ),
            )

        self.assertEqual(
            events,
            [
                "reconcile",
                "monitor",
                "execute",
            ],
        )

    def test_one_monitor_failure_blocks_other_actionable_exit(
        self,
    ) -> None:
        events = []

        coordinator = FakeCoordinator(
            events
        )

        failed = PositionMonitorOutcome(
            position_id="position-aapl",
            symbol="AAPL",
            error=RuntimeError(
                "AAPL quote failed"
            ),
        )

        actionable = (
            make_actionable_outcome(
                position_id="position-msft",
                symbol="MSFT",
            )
        )

        with self.assertRaisesRegex(
            RobinhoodEquityExitCycleError,
            "monitoring failed",
        ):
            run_robinhood_equity_exit_cycle(
                account_number=(
                    "agentic-account"
                ),
                reconciler=(
                    FakeReconciler(events)
                ),
                monitor=(
                    FakeMonitor(
                        events,
                        [
                            failed,
                            actionable,
                        ],
                    )
                ),
                execution_coordinator=(
                    coordinator
                ),
            )

        self.assertEqual(
            coordinator.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()