import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from unittest.mock import (
    Mock,
    patch,
)

from stock_agent.orchestration.robinhood_live_readiness import (
    RobinhoodLiveReadinessResult,
    RobinhoodLiveReadinessStatus,
)
from stock_agent.cli.robinhood_live_readiness import (
    main,
    run_readiness_command,
)


_EVALUATED_AT = datetime(
    2026,
    10,
    5,
    18,
    0,
    tzinfo=timezone.utc,
)


def readiness_result(
    *,
    ready: bool,
) -> RobinhoodLiveReadinessResult:
    return RobinhoodLiveReadinessResult(
        status=(
            RobinhoodLiveReadinessStatus.READY
            if ready
            else RobinhoodLiveReadinessStatus.BLOCKED
        ),
        exit_recovery_clear=ready,
        entry_recovery_clear=ready,
        activation_clear=ready,
        preflight_clear=ready,
        daily_limit_clear=ready,
        daily_reserved_notional=(
            Decimal("0")
        ),
        requested_order_notional=(
            Decimal("5")
        ),
        blockers=(
            ()
            if ready
            else (
                "test blocker",
            )
        ),
        preflight_blockers=(
            ()
            if ready
            else (
                "outside_entry_window",
            )
        ),
    )


class RobinhoodLiveReadinessCliTests(
    unittest.TestCase
):
    def test_default_arguments_check_five_dollar_order(
        self,
    ) -> None:
        expected = readiness_result(
            ready=True
        )

        checker = Mock(
            return_value=expected
        )

        result = run_readiness_command(
            [
                "--account-number",
                "agentic-account",
            ],
            checker=checker,
            clock=lambda: _EVALUATED_AT,
            environ={},
        )

        self.assertIs(
            result,
            expected,
        )

        checker.assert_called_once_with(
            account_number=(
                "agentic-account"
            ),
            evaluated_at=(
                _EVALUATED_AT
            ),
            not_found_grace_period=(
                timedelta(
                    seconds=120
                )
            ),
            requested_order_notional=(
                Decimal("5")
            ),
            minimum_cash_reserve=(
                Decimal("5")
            ),
            env={},
        )

    def test_custom_readiness_arguments_are_forwarded(
        self,
    ) -> None:
        expected = readiness_result(
            ready=True
        )

        checker = Mock(
            return_value=expected
        )

        run_readiness_command(
            [
                "--account-number",
                "agentic-account",
                "--order-notional",
                "4.50",
                "--minimum-cash-reserve",
                "10",
                "--not-found-grace-seconds",
                "300",
            ],
            checker=checker,
            clock=lambda: _EVALUATED_AT,
            environ={},
        )

        checker.assert_called_once_with(
            account_number=(
                "agentic-account"
            ),
            evaluated_at=(
                _EVALUATED_AT
            ),
            not_found_grace_period=(
                timedelta(
                    seconds=300
                )
            ),
            requested_order_notional=(
                Decimal("4.50")
            ),
            minimum_cash_reserve=(
                Decimal("10")
            ),
            env={},
        )

    def test_environment_is_preserved_for_readiness_service(
        self,
    ) -> None:
        expected = readiness_result(
            ready=True
        )

        checker = Mock(
            return_value=expected
        )

        ambient_env = {
            "STOCK_AGENT_RUNTIME_MODE":
                "live",
            "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                "true",
            "ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH":
                "/tmp/entry.sqlite3",
        }

        run_readiness_command(
            [
                "--account-number",
                "agentic-account",
            ],
            checker=checker,
            clock=lambda: _EVALUATED_AT,
            environ=ambient_env,
        )

        passed_env = (
            checker
            .call_args
            .kwargs["env"]
        )

        self.assertEqual(
            passed_env,
            ambient_env,
        )

        self.assertIsNot(
            passed_env,
            ambient_env,
        )

        # The CLI does not mutate the caller's
        # environment. Safety override belongs
        # inside the readiness service.
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

    def test_naive_clock_fails_before_checker(
        self,
    ) -> None:
        checker = Mock()

        with self.assertRaisesRegex(
            ValueError,
            "timezone-aware",
        ):
            run_readiness_command(
                [
                    "--account-number",
                    "agentic-account",
                ],
                checker=checker,
                clock=lambda: datetime(
                    2026,
                    10,
                    5,
                    18,
                    0,
                ),
                environ={},
            )

        checker.assert_not_called()

    @patch(
        "stock_agent.cli."
        "robinhood_live_readiness."
        "run_readiness_command"
    )
    @patch(
        "builtins.print"
    )
    def test_main_returns_zero_when_ready(
        self,
        mock_print,
        run_command,
    ) -> None:
        run_command.return_value = (
            readiness_result(
                ready=True
            )
        )

        exit_code = main(
            []
        )

        self.assertEqual(
            exit_code,
            0,
        )

        mock_print.assert_called_once()

    @patch(
        "stock_agent.cli."
        "robinhood_live_readiness."
        "run_readiness_command"
    )
    @patch(
        "builtins.print"
    )
    def test_main_returns_one_when_blocked(
        self,
        mock_print,
        run_command,
    ) -> None:
        run_command.return_value = (
            readiness_result(
                ready=False
            )
        )

        exit_code = main(
            []
        )

        self.assertEqual(
            exit_code,
            1,
        )

        printed = (
            mock_print
            .call_args
            .args[0]
        )

        self.assertIn(
            "BLOCKED",
            printed,
        )

        self.assertIn(
            "test blocker",
            printed,
        )

        self.assertIn(
            "outside_entry_window",
            printed,
        )


if __name__ == "__main__":
    unittest.main()