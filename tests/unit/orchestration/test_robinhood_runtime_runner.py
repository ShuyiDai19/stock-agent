import unittest
from unittest.mock import Mock
from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from stock_agent.orchestration.robinhood_runtime_runner import (
    run_robinhood_equity_runtime_once,
)
from stock_agent.orchestration.robinhood_strategy_cycle import (
    DEFAULT_ENTRY_BUDGET,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)


_EVALUATED_AT = datetime(
    2026,
    10,
    5,
    18,
    0,
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


class RobinhoodRuntimeRunnerTests(
    unittest.TestCase
):
    def test_safe_runtime_remains_safe(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=False,
            live_execution_enabled=False,
        )

        @contextmanager
        def runtime_opener(**kwargs):
            yield runtime

        cycle_result = object()

        cycle_runner = Mock(
            return_value=cycle_result
        )

        result = (
            run_robinhood_equity_runtime_once(
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                not_found_grace_period=(
                    timedelta(seconds=120)
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
            )
        )

        self.assertFalse(
            result.live_execution_requested
        )

        self.assertFalse(
            result.live_execution_enabled
        )

        self.assertIs(
            result.cycle,
            cycle_result,
        )

        cycle_runner.assert_called_once_with(
            runtime,
            allowed_symbols=(
                "AAPL",
            ),
            universe_policy=_POLICY,
            evaluated_at=(
                _EVALUATED_AT
            ),
            budget=DEFAULT_ENTRY_BUDGET,
        )

    def test_blocked_live_runtime_remains_blocked(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=True,
            live_execution_enabled=False,
        )

        @contextmanager
        def runtime_opener(**kwargs):
            yield runtime

        cycle_result = object()

        cycle_runner = Mock(
            return_value=cycle_result
        )

        result = (
            run_robinhood_equity_runtime_once(
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                not_found_grace_period=(
                    timedelta(seconds=120)
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
            )
        )

        self.assertTrue(
            result.live_execution_requested
        )

        self.assertFalse(
            result.live_execution_enabled
        )

        self.assertIs(
            result.cycle,
            cycle_result,
        )

        cycle_runner.assert_called_once()

    def test_effective_live_runtime_is_reported_as_live(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=True,
            live_execution_enabled=True,
        )

        @contextmanager
        def runtime_opener(**kwargs):
            yield runtime

        cycle_result = object()

        cycle_runner = Mock(
            return_value=cycle_result
        )

        result = (
            run_robinhood_equity_runtime_once(
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                not_found_grace_period=(
                    timedelta(seconds=120)
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
            )
        )

        self.assertTrue(
            result.live_execution_requested
        )

        self.assertTrue(
            result.live_execution_enabled
        )

        self.assertIs(
            result.cycle,
            cycle_result,
        )

        cycle_runner.assert_called_once()

    def test_naive_evaluated_at_fails_before_runtime_opens(
        self,
    ) -> None:
        runtime_opener = Mock()
        cycle_runner = Mock()

        with self.assertRaisesRegex(
            ValueError,
            "evaluated_at must be timezone-aware",
        ):
            run_robinhood_equity_runtime_once(
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=_POLICY,
                not_found_grace_period=(
                    timedelta(seconds=120)
                ),
                evaluated_at=datetime(
                    2026,
                    10,
                    5,
                    18,
                    0,
                ),
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
            )

        runtime_opener.assert_not_called()
        cycle_runner.assert_not_called()

    def test_forwards_execution_clock_to_cycle_runner(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=False,
            live_execution_enabled=False,
        )

        expected = object()

        cycle_calls = []

        @contextmanager
        def runtime_opener(
            **kwargs,
        ):
            yield runtime

        def cycle_runner(
            received_runtime,
            **kwargs,
        ):
            cycle_calls.append(
                (
                    received_runtime,
                    kwargs,
                )
            )

            return expected

        execution_clock = Mock()

        result = (
            run_robinhood_equity_runtime_once(
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _POLICY
                ),
                not_found_grace_period=(
                    timedelta(
                        seconds=120
                    )
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                budget=Decimal("5"),
                env={},
                execution_clock=(
                    execution_clock
                ),
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
            )
        )

        self.assertIs(
            result.cycle,
            expected,
        )

        self.assertEqual(
            len(cycle_calls),
            1,
        )

        (
            received_runtime,
            kwargs,
        ) = cycle_calls[0]

        self.assertIs(
            received_runtime,
            runtime,
        )

        self.assertIs(
            kwargs[
                "execution_clock"
            ],
            execution_clock,
        )

        self.assertEqual(
            kwargs[
                "evaluated_at"
            ],
            _EVALUATED_AT,
        )


if __name__ == "__main__":
    unittest.main()