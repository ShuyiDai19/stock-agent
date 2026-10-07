import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
)
from stock_agent.orchestration.robinhood_equity_exit_cycle import (
    RobinhoodEquityExitCycleResult,
    RobinhoodEquityExitCycleStatus,
)
from stock_agent.orchestration.robinhood_runtime_cycle import (
    run_robinhood_equity_cycle_from_runtime,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)


_EVALUATED_AT = datetime(
    2026,
    9,
    18,
    13,
    47,
    tzinfo=timezone.utc,
)

_POLICY = EquityUniverseScreeningPolicy(
    min_average_volume_30d=Decimal(
        "1000000"
    ),
    min_market_cap=Decimal(
        "1000000000"
    ),
)


class FakeEntryResult:
    def __init__(
        self,
        *,
        execution_mode=(
            EquityEntryExecutionMode
            .REVIEW_ONLY
        ),
        placement_count=0,
        placement_failure_count=0,
    ) -> None:
        self.execution_mode = (
            execution_mode
        )
        self.placement_count = (
            placement_count
        )
        self.placement_failure_count = (
            placement_failure_count
        )


def make_no_action_exit_result(
) -> RobinhoodEquityExitCycleResult:
    return RobinhoodEquityExitCycleResult(
        status=(
            RobinhoodEquityExitCycleStatus
            .NO_ACTION
        ),
        monitored_position_count=0,
        actionable_exit_count=0,
        execution_result=None,
    )


def make_previewed_exit_result(
) -> RobinhoodEquityExitCycleResult:
    return RobinhoodEquityExitCycleResult(
        status=(
            RobinhoodEquityExitCycleStatus
            .PREVIEWED
        ),
        monitored_position_count=1,
        actionable_exit_count=1,
        execution_result=(
            ExecutionResult(
                position_id=(
                    "position-1"
                ),
                status=(
                    ExecutionStatus
                    .PREVIEWED
                ),
                submitted_at=(
                    _EVALUATED_AT
                ),
            )
        ),
    )


def make_submitted_exit_result(
) -> RobinhoodEquityExitCycleResult:
    return RobinhoodEquityExitCycleResult(
        status=(
            RobinhoodEquityExitCycleStatus
            .SUBMITTED
        ),
        monitored_position_count=1,
        actionable_exit_count=1,
        execution_result=(
            ExecutionResult(
                position_id=(
                    "position-1"
                ),
                status=(
                    ExecutionStatus
                    .SUBMITTED
                ),
                submitted_at=(
                    _EVALUATED_AT
                ),
                broker_order_id=(
                    "broker-order-1"
                ),
            )
        ),
    )


class RobinhoodRuntimeCycleTests(
    unittest.TestCase
):
    def test_blocked_live_runtime_runs_review_only(
        self,
    ) -> None:
        invoker = object()
        store = object()

        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=invoker,
            position_store=store,

            # User requested LIVE, but runtime
            # safety gate blocked it.
            live_execution_requested=True,
            live_execution_enabled=False,

            entry_placer=None,
            entry_recovery_service=object(),
            entry_activation_reconciler=(
                object()
            ),
            entry_preflight_reader=(
                object()
            ),
        )

        expected = FakeEntryResult(
            execution_mode=(
                EquityEntryExecutionMode
                .REVIEW_ONLY
            ),
        )

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock(
            return_value=expected
        )

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )
        )

        self.assertIs(
            result.entry_result,
            expected,
        )

        self.assertFalse(
            result.exit_order_submitted
        )

        exit_runner.assert_called_once_with(
            runtime,
            evaluated_at=(
                _EVALUATED_AT
            ),
        )

        kwargs = (
            entry_runner
            .call_args
            .kwargs
        )

        self.assertNotIn(
            "candidate_loader",
            kwargs,
        )

        self.assertEqual(
            kwargs["execution_mode"],
            EquityEntryExecutionMode
            .REVIEW_ONLY,
        )

        self.assertIsNone(
            kwargs["placer"]
        )

        self.assertIsNone(
            kwargs[
                "entry_recovery_service"
            ]
        )

        self.assertIsNone(
            kwargs[
                "activation_reconciler"
            ]
        )

        self.assertIsNone(
            kwargs[
                "preflight_reader"
            ]
        )

        self.assertIsNone(
            kwargs[
                "preflight_opening_debit"
            ]
        )

        self.assertEqual(
            kwargs["account_number"],
            "agentic-account",
        )

        self.assertIs(
            entry_runner
            .call_args
            .args[0],
            invoker,
        )

        self.assertIs(
            entry_runner
            .call_args
            .args[1],
            store,
        )

    def test_live_runtime_forwards_safe_entry_lifecycle(
        self,
    ) -> None:
        invoker = object()
        store = object()
        placer = object()
        recovery_service = object()
        activation_reconciler = object()
        preflight_reader = object()
        budget = Decimal("10")

        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=invoker,
            position_store=store,
            live_execution_requested=True,
            live_execution_enabled=True,
            entry_placer=placer,
            entry_recovery_service=(
                recovery_service
            ),
            entry_activation_reconciler=(
                activation_reconciler
            ),
            entry_preflight_reader=(
                preflight_reader
            ),
        )

        expected = FakeEntryResult(
            execution_mode=(
                EquityEntryExecutionMode
                .LIVE
            ),
        )

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock(
            return_value=expected
        )

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                budget=budget,
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )
        )

        self.assertIs(
            result.entry_result,
            expected,
        )

        self.assertEqual(
            result.exit_result.status,
            RobinhoodEquityExitCycleStatus
            .NO_ACTION,
        )

        kwargs = (
            entry_runner
            .call_args
            .kwargs
        )

        self.assertNotIn(
            "candidate_loader",
            kwargs,
        )

        self.assertEqual(
            kwargs["execution_mode"],
            EquityEntryExecutionMode
            .LIVE,
        )

        self.assertIs(
            kwargs["placer"],
            placer,
        )

        self.assertIs(
            kwargs[
                "entry_recovery_service"
            ],
            recovery_service,
        )

        self.assertIs(
            kwargs[
                "activation_reconciler"
            ],
            activation_reconciler,
        )

        self.assertIs(
            kwargs[
                "preflight_reader"
            ],
            preflight_reader,
        )

        self.assertEqual(
            kwargs[
                "preflight_opening_debit"
            ],
            budget,
        )

    def test_live_runtime_without_placer_fails_closed(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=object(),
            position_store=object(),
            live_execution_requested=True,
            live_execution_enabled=True,
            entry_placer=None,
            entry_recovery_service=object(),
            entry_activation_reconciler=(
                object()
            ),
            entry_preflight_reader=(
                object()
            ),
        )

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock()

        with self.assertRaisesRegex(
            RuntimeError,
            "missing entry placer",
        ):
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )

        exit_runner.assert_called_once()

        entry_runner.assert_not_called()

    def test_live_runtime_without_preflight_reader_fails_closed(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=object(),
            position_store=object(),
            live_execution_requested=True,
            live_execution_enabled=True,
            entry_placer=object(),
            entry_recovery_service=object(),
            entry_activation_reconciler=(
                object()
            ),
            entry_preflight_reader=None,
        )

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock()

        with self.assertRaisesRegex(
            RuntimeError,
            "missing entry preflight reader",
        ):
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )

        exit_runner.assert_called_once()

        entry_runner.assert_not_called()

    def test_live_runtime_without_recovery_service_fails_closed(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=object(),
            position_store=object(),
            live_execution_requested=True,
            live_execution_enabled=True,
            entry_placer=object(),
            entry_recovery_service=None,
            entry_activation_reconciler=(
                object()
            ),
            entry_preflight_reader=object(),
        )

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock()

        with self.assertRaisesRegex(
            RuntimeError,
            "missing entry recovery service",
        ):
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )

        exit_runner.assert_called_once()
        entry_runner.assert_not_called()

    def test_live_runtime_without_activation_reconciler_fails_closed(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=object(),
            position_store=object(),
            live_execution_requested=True,
            live_execution_enabled=True,
            entry_placer=object(),
            entry_recovery_service=object(),
            entry_activation_reconciler=None,
            entry_preflight_reader=object(),
        )

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock()

        with self.assertRaisesRegex(
            RuntimeError,
            "missing entry activation reconciler",
        ):
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )

        exit_runner.assert_called_once()
        entry_runner.assert_not_called()

    def test_submitted_exit_stops_before_entry(
        self,
    ) -> None:
        runtime = SimpleNamespace()

        exit_runner = Mock(
            return_value=(
                make_submitted_exit_result()
            )
        )

        entry_runner = Mock(
            side_effect=AssertionError(
                "entry must not run after "
                "submitted exit"
            )
        )

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )
        )

        self.assertTrue(
            result.exit_order_submitted
        )

        self.assertIsNone(
            result.entry_result
        )

        self.assertEqual(
            result.exit_result.status,
            RobinhoodEquityExitCycleStatus
            .SUBMITTED,
        )

        exit_runner.assert_called_once_with(
            runtime,
            evaluated_at=(
                _EVALUATED_AT
            ),
        )

        entry_runner.assert_not_called()

    def test_previewed_exit_stops_before_entry(
        self,
    ) -> None:
        runtime = SimpleNamespace()

        exit_runner = Mock(
            return_value=(
                make_previewed_exit_result()
            )
        )

        entry_runner = Mock(
            side_effect=AssertionError(
                "entry must not run after "
                "previewed exit"
            )
        )

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )
        )

        self.assertTrue(
            result.exit_previewed
        )

        self.assertFalse(
            result.exit_order_submitted
        )

        self.assertIsNone(
            result.entry_result
        )

        entry_runner.assert_not_called()

    def test_no_exit_runs_entry_after_exit(
        self,
    ) -> None:
        events = []

        invoker = object()
        store = object()

        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=invoker,
            position_store=store,
            live_execution_requested=False,
            live_execution_enabled=False,
            entry_placer=None,
            entry_recovery_service=None,
            entry_activation_reconciler=None,
            entry_preflight_reader=None,
        )

        expected = FakeEntryResult()

        def exit_runner(
            received_runtime,
            *,
            evaluated_at,
        ):
            self.assertIs(
                received_runtime,
                runtime,
            )

            events.append(
                "exit"
            )

            return (
                make_no_action_exit_result()
            )

        def entry_runner(
            *args,
            **kwargs,
        ):
            events.append(
                "entry"
            )

            return expected

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )
        )

        self.assertEqual(
            events,
            [
                "exit",
                "entry",
            ],
        )

        self.assertIs(
            result.entry_result,
            expected,
        )

        self.assertEqual(
            result.exit_result.status,
            RobinhoodEquityExitCycleStatus
            .NO_ACTION,
        )

    def test_exit_failure_blocks_entry(
        self,
    ) -> None:
        events = []

        runtime = SimpleNamespace()

        def exit_runner(
            received_runtime,
            *,
            evaluated_at,
        ):
            events.append(
                "exit"
            )

            raise RuntimeError(
                "exit reconciliation failed"
            )

        def entry_runner(
            *args,
            **kwargs,
        ):
            events.append(
                "entry"
            )

            raise AssertionError(
                "entry must not run"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "exit reconciliation failed",
        ):
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                evaluated_at=(
                    _EVALUATED_AT
                ),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
            )

        self.assertEqual(
            events,
            [
                "exit",
            ],
        )

    def test_passes_candidate_loader_to_entry_cycle(
        self,
    ) -> None:
        invoker = object()
        store = object()
        candidate_loader = object()

        runtime = SimpleNamespace(
            account_number=(
                "agentic-account"
            ),
            _strategy_invoker=invoker,
            position_store=store,
            live_execution_requested=False,
            live_execution_enabled=False,
            entry_placer=None,
            entry_recovery_service=None,
            entry_activation_reconciler=None,
            entry_preflight_reader=None,
        )

        expected = FakeEntryResult()

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock(
            return_value=expected
        )

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _POLICY
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                budget=Decimal("8"),
                exit_cycle_runner=(
                    exit_runner
                ),
                entry_cycle_runner=(
                    entry_runner
                ),
                candidate_loader=(
                    candidate_loader
                ),
            )
        )

        entry_runner.assert_called_once()

        kwargs = (
            entry_runner
            .call_args
            .kwargs
        )

        self.assertIs(
            kwargs[
                "candidate_loader"
            ],
            candidate_loader,
        )

        self.assertEqual(
            kwargs[
                "allowed_symbols"
            ],
            (
                "AAPL",
            ),
        )

        self.assertEqual(
            kwargs[
                "budget"
            ],
            Decimal("8"),
        )

        self.assertIs(
            result.entry_result,
            expected,
        )

    def test_forwards_execution_clock_to_entry_cycle(
        self,
    ) -> None:
        invoker = object()
        store = object()

        runtime = SimpleNamespace(
            account_number="agentic-account",
            _strategy_invoker=invoker,
            position_store=store,
            live_execution_requested=False,
            live_execution_enabled=False,
            entry_placer=None,
            entry_recovery_service=None,
            entry_activation_reconciler=None,
            entry_preflight_reader=None,
        )

        expected = FakeEntryResult()

        exit_runner = Mock(
            return_value=(
                make_no_action_exit_result()
            )
        )

        entry_runner = Mock(
            return_value=expected
        )

        execution_clock = Mock()

        run_robinhood_equity_cycle_from_runtime(
            runtime,
            allowed_symbols=("AAPL",),
            universe_policy=_POLICY,
            evaluated_at=_EVALUATED_AT,
            exit_cycle_runner=exit_runner,
            entry_cycle_runner=entry_runner,
            execution_clock=execution_clock,
        )

        self.assertIs(
            entry_runner
            .call_args
            .kwargs["execution_clock"],
            execution_clock,
        )


if __name__ == "__main__":
    unittest.main()