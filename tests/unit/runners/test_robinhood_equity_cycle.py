import unittest
from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from types import SimpleNamespace

from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
)
from stock_agent.runners.robinhood_equity_cycle import (
    PRODUCTION_ALLOWED_SYMBOLS,
    PRODUCTION_UNIVERSE_POLICY,
    format_cycle_result,
    resolve_not_found_grace_period,
    resolve_robinhood_account_number,
    resolve_mcp_startup_timeout_seconds,
    run_production_robinhood_equity_cycle,
    format_entry_rejection_diagnostics,
)
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightBlocker,
    EquityEntryPreflightResult,
)
from stock_agent.orchestration.equity_entry_preflight_service import (
    EquityEntryPreflightBlockedError,
)
from stock_agent.runners.robinhood_equity_cycle import (
    main,
)
from stock_agent.risk.entry_portfolio import (
    EntryRiskReason,
)
from stock_agent.strategy.entry_confirmation import (
    EntryConfirmationReason,
)


_NOW = datetime(
    2026,
    9,
    23,
    15,
    0,
    tzinfo=timezone.utc,
)


class FakeEntryOutcome:
    def __init__(
        self,
        *,
        execution_mode=(
            EquityEntryExecutionMode
            .REVIEW_ONLY
        ),
        placement_count=0,
        placement_failure_count=0,
        universe_eligible_symbols=(),
        universe_rejected_count=0,
        universe_error_count=0,
        loaded_candidate_count=0,
        eligible_entry_count=0,
        market_data_error_count=0,
        review_error_count=0,
        placement_blocked_count=0,
    ) -> None:
        self.execution_mode = execution_mode
        self.placement_count = placement_count
        self.placement_failure_count = (
            placement_failure_count
        )

        self.universe_eligible_symbols = (
            universe_eligible_symbols
        )
        self.universe_rejected_count = (
            universe_rejected_count
        )
        self.universe_error_count = (
            universe_error_count
        )
        self.loaded_candidate_count = (
            loaded_candidate_count
        )
        self.eligible_entry_count = (
            eligible_entry_count
        )
        self.market_data_error_count = (
            market_data_error_count
        )
        self.review_error_count = (
            review_error_count
        )
        self.placement_blocked_count = (
            placement_blocked_count
        )


class FakeRuntimeOutcome:
    def __init__(
        self,
        *,
        entry_result=None,
        exit_order_submitted=False,
        exit_previewed=False,
    ) -> None:
        self.entry_result = entry_result
        self.exit_order_submitted = (
            exit_order_submitted
        )
        self.exit_previewed = (
            exit_previewed
        )

    @property
    def entry_order_submitted(
        self,
    ) -> bool:
        if self.entry_result is None:
            return False

        return (
            self.entry_result
            .placement_count
            > 0
        )

    @property
    def placement_count(
        self,
    ) -> int:
        if self.entry_result is None:
            return 0

        return (
            self.entry_result
            .placement_count
        )

    @property
    def placement_failure_count(
        self,
    ) -> int:
        if self.entry_result is None:
            return 0

        return (
            self.entry_result
            .placement_failure_count
        )

class RobinhoodEquityProductionRunnerTests(
    unittest.TestCase
):
    def test_requires_account_number(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ROBINHOOD_ACCOUNT_NUMBER",
        ):
            resolve_robinhood_account_number(
                {}
            )

    def test_rejects_empty_account_number(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must not be empty",
        ):
            resolve_robinhood_account_number(
                {
                    "ROBINHOOD_ACCOUNT_NUMBER":
                        "   ",
                }
            )

    def test_resolves_account_number(
        self,
    ) -> None:
        self.assertEqual(
            resolve_robinhood_account_number(
                {
                    "ROBINHOOD_ACCOUNT_NUMBER":
                        " agentic-account ",
                }
            ),
            "agentic-account",
        )

    def test_requires_recovery_grace_period(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ROBINHOOD_NOT_FOUND_GRACE_SECONDS",
        ):
            resolve_not_found_grace_period(
                {}
            )

    def test_resolves_recovery_grace_period(
        self,
    ) -> None:
        self.assertEqual(
            resolve_not_found_grace_period(
                {
                    "ROBINHOOD_NOT_FOUND_GRACE_SECONDS":
                        "120",
                }
            ),
            timedelta(
                seconds=120
            ),
        )

    def test_rejects_negative_recovery_grace_period(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "non-negative integer",
        ):
            resolve_not_found_grace_period(
                {
                    "ROBINHOOD_NOT_FOUND_GRACE_SECONDS":
                        "-1",
                }
            )

    def test_runs_runtime_owned_cycle(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=True,
            live_execution_enabled=True,
        )

        opener_calls = []
        cycle_calls = []

        @contextmanager
        def runtime_opener(
            **kwargs,
        ):
            opener_calls.append(
                kwargs
            )
            yield runtime

        expected = FakeRuntimeOutcome(
            entry_result=FakeEntryOutcome(
                execution_mode=(
                    EquityEntryExecutionMode.LIVE
                ),
            )
        )

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

        env = {
            "ROBINHOOD_ACCOUNT_NUMBER":
                "agentic-account",
            "ROBINHOOD_NOT_FOUND_GRACE_SECONDS":
                "120",
            "STOCK_AGENT_RUNTIME_MODE":
                "live",
            "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                "true",
            "ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS":
                "180",
        }

        result = (
            run_production_robinhood_equity_cycle(
                env=env,
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
                clock=lambda: _NOW,
            )
        )

        self.assertIs(
            result,
            expected,
        )

        self.assertEqual(
            opener_calls,
            [
                {
                    "account_number":
                        "agentic-account",
                    "not_found_grace_period":
                        timedelta(
                            seconds=120
                        ),
                    "env": env,
                    "startup_timeout_seconds":
                        180,
                }
            ],
        )

        self.assertEqual(
            len(
                cycle_calls
            ),
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

        self.assertEqual(
            kwargs[
                "allowed_symbols"
            ],
            PRODUCTION_ALLOWED_SYMBOLS,
        )

        self.assertIs(
            kwargs[
                "universe_policy"
            ],
            PRODUCTION_UNIVERSE_POLICY,
        )

        self.assertEqual(
            kwargs[
                "evaluated_at"
            ],
            _NOW,
        )

        self.assertEqual(
            kwargs[
                "budget"
            ],
            Decimal("8"),
        )

    def test_live_requested_but_blocked_fails_closed(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=True,
            live_execution_enabled=False,
        )

        cycle_calls = []

        @contextmanager
        def runtime_opener(
            **kwargs,
        ):
            yield runtime

        def cycle_runner(
            *args,
            **kwargs,
        ):
            cycle_calls.append(
                (
                    args,
                    kwargs,
                )
            )

            raise AssertionError(
                "cycle must not run when "
                "startup safety blocked LIVE"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "startup safety recovery",
        ):
            run_production_robinhood_equity_cycle(
                env={
                    "ROBINHOOD_ACCOUNT_NUMBER":
                        "agentic-account",
                    "ROBINHOOD_NOT_FOUND_GRACE_SECONDS":
                        "120",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                },
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
                clock=lambda: _NOW,
            )

        self.assertEqual(
            cycle_calls,
            [],
        )

    def test_placement_failure_is_process_failure(
        self,
    ) -> None:
        runtime = SimpleNamespace(
            live_execution_requested=True,
            live_execution_enabled=True,
        )

        @contextmanager
        def runtime_opener(
            **kwargs,
        ):
            yield runtime

        def cycle_runner(
            *args,
            **kwargs,
        ):
            return FakeRuntimeOutcome(
                entry_result=FakeEntryOutcome(
                    execution_mode=(
                        EquityEntryExecutionMode.LIVE
                    ),
                    placement_failure_count=1,
                )
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "placement failure",
        ):
            run_production_robinhood_equity_cycle(
                env={
                    "ROBINHOOD_ACCOUNT_NUMBER":
                        "agentic-account",
                    "ROBINHOOD_NOT_FOUND_GRACE_SECONDS":
                        "120",
                },
                runtime_opener=(
                    runtime_opener
                ),
                cycle_runner=(
                    cycle_runner
                ),
                clock=lambda: _NOW,
            )

    def test_formats_live_no_action_result(
        self,
    ) -> None:
        result = FakeRuntimeOutcome(
            entry_result=FakeEntryOutcome(
                execution_mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                placement_count=0,
            )
        )

        self.assertFalse(
            result.entry_order_submitted
        )

        self.assertEqual(
            format_cycle_result(result),
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "NO ACTION"
            ),
        )


    def test_formats_submitted_entry_result(
        self,
    ) -> None:
        result = FakeRuntimeOutcome(
            entry_result=FakeEntryOutcome(
                execution_mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                placement_count=1,
            )
        )

        self.assertEqual(
            format_cycle_result(result),
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "OPENING ORDER SUBMITTED"
            ),
        )

    def test_main_treats_normal_preflight_block_as_no_action(
        self,
    ) -> None:
        blocked = (
            EquityEntryPreflightBlockedError(
                EquityEntryPreflightResult(
                    blockers=(
                        EquityEntryPreflightBlocker
                        .EXISTING_POSITION,
                    )
                )
            )
        )

        output = StringIO()

        with patch(
            "stock_agent.runners."
            "robinhood_equity_cycle."
            "run_production_robinhood_equity_cycle",
            side_effect=blocked,
        ):
            with redirect_stdout(
                output
            ):
                exit_code = main()

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            output.getvalue().strip(),
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "NO ACTION"
            ),
        )

    def test_main_fails_closed_when_preflight_data_is_unavailable(
        self,
    ) -> None:
        blocked = (
            EquityEntryPreflightBlockedError(
                EquityEntryPreflightResult(
                    blockers=(
                        EquityEntryPreflightBlocker
                        .DATA_UNAVAILABLE,
                    )
                )
            )
        )

        with patch(
            "stock_agent.runners."
            "robinhood_equity_cycle."
            "run_production_robinhood_equity_cycle",
            side_effect=blocked,
        ):
            with self.assertRaises(
                EquityEntryPreflightBlockedError
            ):
                main()

    def test_main_prints_closing_order_submitted(
        self,
    ) -> None:
        result = FakeRuntimeOutcome(
            entry_result=None,
            exit_order_submitted=True,
        )

        with patch(
            "stock_agent.runners."
            "robinhood_equity_cycle."
            "run_production_robinhood_equity_cycle",
            return_value=result,
        ):
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main()

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            output.getvalue().strip(),
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "CLOSING ORDER SUBMITTED"
            ),
        )

    def test_formats_submitted_exit_result(
        self,
    ) -> None:
        result = FakeRuntimeOutcome(
            entry_result=None,
            exit_order_submitted=True,
        )

        self.assertEqual(
            format_cycle_result(result),
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "CLOSING ORDER SUBMITTED"
            ),
        )

    def test_formats_previewed_exit_as_review_only(
        self,
    ) -> None:
        result = FakeRuntimeOutcome(
            entry_result=None,
            exit_previewed=True,
        )

        self.assertEqual(
            format_cycle_result(result),
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "REVIEW ONLY"
            ),
        )

    def test_main_prints_no_action_diagnostics(
        self,
    ) -> None:
        entry_result = FakeEntryOutcome(
            execution_mode=(
                EquityEntryExecutionMode
                .LIVE
            ),
            placement_count=0,
            universe_eligible_symbols=(
                "AAPL",
                "MSFT",
            ),
            universe_rejected_count=1,
            universe_error_count=0,
            loaded_candidate_count=2,
            eligible_entry_count=0,
            market_data_error_count=0,
            review_error_count=0,
            placement_blocked_count=0,
        )

        result = FakeRuntimeOutcome(
            entry_result=entry_result,
        )

        with patch(
            "stock_agent.runners."
            "robinhood_equity_cycle."
            "run_production_robinhood_equity_cycle",
            return_value=result,
        ):
            output = StringIO()

            with redirect_stdout(
                output
            ):
                exit_code = main()

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                (
                    "EQUITY ENTRY CYCLE RESULT: "
                    "NO ACTION"
                ),
                (
                    "EQUITY ENTRY DIAGNOSTICS: "
                    "universe_selected=2 "
                    "universe_rejected=1 "
                    "universe_errors=0 "
                    "loaded_candidates=2 "
                    "eligible_entries=0 "
                    "market_data_errors=0 "
                    "review_errors=0 "
                    "placement_blocked=0"
                ),
            ],
        )

    def test_formats_entry_rejection_diagnostics(
        self,
    ) -> None:
        rejected_item = SimpleNamespace(
            symbol="AAPL",
            error=None,
            outcome=SimpleNamespace(
                eligible_to_place=False,
                decision=SimpleNamespace(
                    confirmation=SimpleNamespace(
                        reasons=frozenset(
                            {
                                EntryConfirmationReason
                                .PRICE_NOT_ABOVE_VWAP,
                            }
                        ),
                    ),
                    risk=SimpleNamespace(
                        reasons=frozenset(
                            {
                                EntryRiskReason
                                .DUPLICATE_UNDERLYING,
                            }
                        ),
                    ),
                ),
                status=SimpleNamespace(
                    value="no_trade",
                ),
                reason=(
                    "entry confirmation or "
                    "portfolio risk rejected"
                ),
            ),
        )

        result = FakeRuntimeOutcome(
            entry_result=SimpleNamespace(
                cycle=SimpleNamespace(
                    strategy=SimpleNamespace(
                        items=(
                            rejected_item,
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(
            format_entry_rejection_diagnostics(
                result
            ),
            (
                (
                    "ENTRY REJECTION: AAPL "
                    "confirmation="
                    "price_not_above_vwap "
                    "risk=duplicate_underlying"
                ),
            ),
        )

    def test_resolves_default_mcp_startup_timeout(
        self,
    ) -> None:
        self.assertEqual(
            resolve_mcp_startup_timeout_seconds(
                {}
            ),
            10,
        )


    def test_resolves_mcp_startup_timeout(
        self,
    ) -> None:
        self.assertEqual(
            resolve_mcp_startup_timeout_seconds(
                {
                    "ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS":
                        "180",
                }
            ),
            180,
        )


    def test_rejects_invalid_mcp_startup_timeout(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "positive integer",
        ):
            resolve_mcp_startup_timeout_seconds(
                {
                    "ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS":
                        "0",
                }
            )


if __name__ == "__main__":
    unittest.main()