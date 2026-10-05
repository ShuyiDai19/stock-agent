import unittest

from datetime import (
    datetime,
    timezone,
)
from unittest.mock import Mock

from stock_agent.cli.robinhood_equity_once import (
    run_operator_command,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
)


_EVALUATED_AT = datetime(
    2026,
    10,
    5,
    19,
    30,
    tzinfo=timezone.utc,
)


class RobinhoodEquityOnceCliTests(
    unittest.TestCase
):
    def test_no_mode_defaults_to_safe(
        self,
    ) -> None:
        expected = object()

        runner = Mock(
            return_value=expected
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

        self.assertIs(
            result,
            expected,
        )

        runner.assert_called_once()

        kwargs = (
            runner.call_args.kwargs
        )

        self.assertEqual(
            kwargs["env"][
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "safe",
        )

        self.assertEqual(
            kwargs["env"][
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "false",
        )

        self.assertEqual(
            kwargs["account_number"],
            "agentic-account",
        )

        self.assertEqual(
            kwargs["allowed_symbols"],
            (
                "AAPL",
            ),
        )

        self.assertEqual(
            kwargs["evaluated_at"],
            _EVALUATED_AT,
        )

        self.assertEqual(
            kwargs["budget"],
            DEFAULT_ENTRY_BUDGET,
        )

    def test_explicit_safe_mode_writes_safe_env(
        self,
    ) -> None:
        expected = object()

        runner = Mock(
            return_value=expected
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
                "UNRELATED_SETTING": "keep-me",
            },
        )

        self.assertIs(
            result,
            expected,
        )

        runner.assert_called_once()

        runtime_env = (
            runner.call_args
            .kwargs["env"]
        )

        self.assertEqual(
            runtime_env[
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "safe",
        )

        self.assertEqual(
            runtime_env[
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "false",
        )

        # Non-runtime environment values
        # should still be preserved.
        self.assertEqual(
            runtime_env[
                "UNRELATED_SETTING"
            ],
            "keep-me",
        )

    def test_live_mode_without_confirmation_fails_before_runner(
        self,
    ) -> None:
        runner = Mock()
        clock = Mock(
            return_value=_EVALUATED_AT
        )

        with self.assertRaises(
            SystemExit
        ) as raised:
            run_operator_command(
                [
                    "--account-number",
                    "agentic-account",
                    "--symbols",
                    "AAPL",
                    "--mode",
                    "live",
                ],
                runner=runner,
                clock=clock,
                environ={},
            )

        self.assertEqual(
            raised.exception.code,
            2,
        )

        # Critical operator-safety invariant:
        # invalid live authorization fails
        # before the runner or clock is used.
        runner.assert_not_called()
        clock.assert_not_called()

    def test_live_mode_with_confirmation_requests_live_env(
        self,
    ) -> None:
        expected = object()

        runner = Mock(
            return_value=expected
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

        self.assertIs(
            result,
            expected,
        )

        runner.assert_called_once()

        kwargs = (
            runner.call_args.kwargs
        )

        runtime_env = kwargs["env"]

        self.assertEqual(
            runtime_env[
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "live",
        )

        self.assertEqual(
            runtime_env[
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "true",
        )

        self.assertEqual(
            kwargs["account_number"],
            "agentic-account",
        )

        self.assertEqual(
            kwargs["allowed_symbols"],
            (
                "AAPL",
            ),
        )

        self.assertEqual(
            kwargs["evaluated_at"],
            _EVALUATED_AT,
        )

        self.assertEqual(
            kwargs["budget"],
            DEFAULT_ENTRY_BUDGET,
        )

    def test_explicit_safe_overrides_ambient_live_environment(
        self,
    ) -> None:
        expected = object()

        runner = Mock(
            return_value=expected
        )

        ambient_env = {
            "STOCK_AGENT_RUNTIME_MODE":
                "live",
            "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                "true",
            "UNRELATED_SETTING":
                "preserved",
        }

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
            environ=ambient_env,
        )

        self.assertIs(
            result,
            expected,
        )

        runner.assert_called_once()

        runtime_env = (
            runner.call_args
            .kwargs["env"]
        )

        # Explicit SAFE operator intent must
        # override stale ambient LIVE settings.
        self.assertEqual(
            runtime_env[
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "safe",
        )

        self.assertEqual(
            runtime_env[
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "false",
        )

        self.assertEqual(
            runtime_env[
                "UNRELATED_SETTING"
            ],
            "preserved",
        )

        # build_runtime_env() must copy the
        # environment rather than mutate the
        # caller-provided mapping.
        self.assertEqual(
            ambient_env[
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "live",
        )

        self.assertEqual(
            ambient_env[
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "true",
        )


if __name__ == "__main__":
    unittest.main()