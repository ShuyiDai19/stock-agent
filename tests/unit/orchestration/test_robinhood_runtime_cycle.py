import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
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
        )

        expected = object()

        with patch(
            "stock_agent.orchestration."
            "robinhood_runtime_cycle."
            "run_robinhood_equity_strategy_cycle_from_store",
            return_value=expected,
        ) as run_cycle:
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
                )
            )

        self.assertIs(
            result,
            expected,
        )

        kwargs = (
            run_cycle.call_args.kwargs
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

        self.assertEqual(
            kwargs["account_number"],
            "agentic-account",
        )

        self.assertIs(
            run_cycle.call_args.args[0],
            invoker,
        )

        self.assertIs(
            run_cycle.call_args.args[1],
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
        )

        expected = object()

        with patch(
            "stock_agent.orchestration."
            "robinhood_runtime_cycle."
            "run_robinhood_equity_strategy_cycle_from_store",
            return_value=expected,
        ) as run_cycle:
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
                )
            )

        self.assertIs(
            result,
            expected,
        )

        kwargs = run_cycle.call_args.kwargs

        self.assertEqual(
            kwargs["execution_mode"],
            EquityEntryExecutionMode.LIVE,
        )

        self.assertIs(
            kwargs["placer"],
            placer,
        )

        self.assertIs(
            kwargs["entry_recovery_service"],
            recovery_service,
        )

        self.assertIs(
            kwargs["activation_reconciler"],
            activation_reconciler,
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
        )

        with patch(
            "stock_agent.orchestration."
            "robinhood_runtime_cycle."
            "run_robinhood_equity_strategy_cycle_from_store",
        ) as run_cycle:
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
                )

            run_cycle.assert_not_called()