import unittest

from contextlib import contextmanager
from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace

from stock_agent.cli.robinhood_equity_once import (
    run_operator_command,
)
from stock_agent.orchestration.robinhood_runtime_runner import (
    run_robinhood_equity_runtime_once,
)


_EVALUATED_AT = datetime(
    2026,
    10,
    5,
    19,
    30,
    tzinfo=timezone.utc,
)


class RobinhoodOperatorBoundaryIntegrationTests(
    unittest.TestCase
):
    def make_boundary_runner(
        self,
        *,
        allow_live: bool,
        captured: dict,
        cycle_result,
    ):
        def runner(
            *,
            account_number,
            allowed_symbols,
            universe_policy,
            not_found_grace_period,
            evaluated_at,
            budget,
            env,
            execution_clock=None,
        ):
            @contextmanager
            def runtime_opener(
                *,
                account_number,
                not_found_grace_period,
                env,
            ):
                requested = (
                    env[
                        "STOCK_AGENT_RUNTIME_MODE"
                    ]
                    == "live"
                    and env[
                        "ROBINHOOD_LIVE_EXECUTION_ENABLED"
                    ]
                    == "true"
                )

                runtime = SimpleNamespace(
                    live_execution_requested=(
                        requested
                    ),
                    live_execution_enabled=(
                        requested
                        and allow_live
                    ),
                )

                captured["runtime_env"] = (
                    dict(env)
                )

                captured["runtime"] = runtime

                yield runtime

            def cycle_runner(
                runtime,
                **kwargs,
            ):
                captured[
                    "cycle_runtime"
                ] = runtime

                captured[
                    "cycle_kwargs"
                ] = kwargs

                return cycle_result

            return (
                run_robinhood_equity_runtime_once(
                    account_number=(
                        account_number
                    ),
                    allowed_symbols=(
                        allowed_symbols
                    ),
                    universe_policy=(
                        universe_policy
                    ),
                    not_found_grace_period=(
                        not_found_grace_period
                    ),
                    evaluated_at=(
                        evaluated_at
                    ),
                    budget=budget,
                    env=env,
                    runtime_opener=(
                        runtime_opener
                    ),
                    cycle_runner=(
                        cycle_runner
                    ),
                )
            )

        return runner

    def test_default_safe_cannot_become_live(
        self,
    ) -> None:
        captured = {}
        cycle_result = object()

        runner = self.make_boundary_runner(
            allow_live=True,
            captured=captured,
            cycle_result=cycle_result,
        )

        result = run_operator_command(
            [
                "--account-number",
                "agentic-account",
                "--symbols",
                "AAPL",
            ],
            runner=runner,
            clock=lambda: _EVALUATED_AT,
            environ={},
        )

        self.assertFalse(
            result.live_execution_requested
        )

        self.assertFalse(
            result.live_execution_enabled
        )

        self.assertEqual(
            captured["runtime_env"][
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "safe",
        )

        self.assertEqual(
            captured["runtime_env"][
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "false",
        )

        self.assertFalse(
            captured["cycle_runtime"]
            .live_execution_enabled
        )

        self.assertIs(
            result.cycle,
            cycle_result,
        )

    def test_explicit_safe_overrides_ambient_live_end_to_end(
        self,
    ) -> None:
        captured = {}
        cycle_result = object()

        runner = self.make_boundary_runner(
            allow_live=True,
            captured=captured,
            cycle_result=cycle_result,
        )

        result = run_operator_command(
            [
                "--account-number",
                "agentic-account",
                "--symbols",
                "AAPL",
                "--mode",
                "safe",
            ],
            runner=runner,
            clock=lambda: _EVALUATED_AT,
            environ={
                "STOCK_AGENT_RUNTIME_MODE":
                    "live",
                "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                    "true",
            },
        )

        self.assertFalse(
            result.live_execution_requested
        )

        self.assertFalse(
            result.live_execution_enabled
        )

        self.assertEqual(
            captured["runtime_env"][
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "safe",
        )

        self.assertEqual(
            captured["runtime_env"][
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "false",
        )

        self.assertFalse(
            captured["cycle_runtime"]
            .live_execution_enabled
        )

    def test_confirmed_live_request_can_still_be_blocked_by_runtime(
        self,
    ) -> None:
        captured = {}
        cycle_result = object()

        # Operator is authorized to request LIVE,
        # but the runtime safety gate rejects it.
        runner = self.make_boundary_runner(
            allow_live=False,
            captured=captured,
            cycle_result=cycle_result,
        )

        result = run_operator_command(
            [
                "--account-number",
                "agentic-account",
                "--symbols",
                "AAPL",
                "--mode",
                "live",
                "--confirm-live",
            ],
            runner=runner,
            clock=lambda: _EVALUATED_AT,
            environ={},
        )

        self.assertTrue(
            result.live_execution_requested
        )

        self.assertFalse(
            result.live_execution_enabled
        )

        self.assertEqual(
            captured["runtime_env"][
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "live",
        )

        self.assertEqual(
            captured["runtime_env"][
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "true",
        )

        # Critical invariant:
        # operator intent must not override
        # the runtime safety decision.
        self.assertTrue(
            captured["cycle_runtime"]
            .live_execution_requested
        )

        self.assertFalse(
            captured["cycle_runtime"]
            .live_execution_enabled
        )

    def test_confirmed_live_request_reaches_cycle_only_when_runtime_allows(
        self,
    ) -> None:
        captured = {}
        cycle_result = object()

        runner = self.make_boundary_runner(
            allow_live=True,
            captured=captured,
            cycle_result=cycle_result,
        )

        result = run_operator_command(
            [
                "--account-number",
                "agentic-account",
                "--symbols",
                "AAPL",
                "--mode",
                "live",
                "--confirm-live",
            ],
            runner=runner,
            clock=lambda: _EVALUATED_AT,
            environ={},
        )

        self.assertTrue(
            result.live_execution_requested
        )

        self.assertTrue(
            result.live_execution_enabled
        )

        self.assertTrue(
            captured["cycle_runtime"]
            .live_execution_requested
        )

        self.assertTrue(
            captured["cycle_runtime"]
            .live_execution_enabled
        )

        self.assertEqual(
            captured["cycle_kwargs"][
                "allowed_symbols"
            ],
            (
                "AAPL",
            ),
        )

        self.assertEqual(
            captured["cycle_kwargs"][
                "evaluated_at"
            ],
            _EVALUATED_AT,
        )

        self.assertIs(
            result.cycle,
            cycle_result,
        )


if __name__ == "__main__":
    unittest.main()