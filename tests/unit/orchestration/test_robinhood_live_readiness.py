import unittest

from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import (
    Mock,
    patch,
)

from stock_agent.orchestration.robinhood_live_readiness import (
    RobinhoodLiveReadinessStatus,
    check_robinhood_live_readiness,
)
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightBlocker,
    EquityEntryPreflightResult,
)
from stock_agent.orchestration.equity_entry_preflight_service import (
    EquityEntryPreflightBlockedError,
)


_EVALUATED_AT = datetime(
    2026,
    10,
    5,
    18,
    0,
    tzinfo=timezone.utc,
)

_GRACE_PERIOD = timedelta(
    seconds=120
)

_ACCOUNT_NUMBER = "agentic-account"


def make_runtime():
    entry_recovery_service = Mock()
    entry_recovery_service.recover.return_value = ()

    entry_activation_reconciler = Mock()

    entry_placement_journal = Mock()
    entry_placement_journal.daily_reserved_notional.return_value = (
        Decimal("0")
    )

    return SimpleNamespace(
        live_execution_requested=False,
        live_execution_enabled=False,
        entry_placer=None,

        recovery=SimpleNamespace(
            has_unresolved_attempts=False,
        ),

        entry_recovery_service=(
            entry_recovery_service
        ),

        entry_activation_reconciler=(
            entry_activation_reconciler
        ),

        entry_preflight_reader=object(),

        entry_placement_journal=(
            entry_placement_journal
        ),
    )


def runtime_opener_for(
    runtime,
    *,
    captured=None,
):
    @contextmanager
    def runtime_opener(
        **kwargs,
    ):
        if captured is not None:
            captured.update(
                kwargs
            )

        yield runtime

    return runtime_opener


class RobinhoodLiveReadinessTests(
    unittest.TestCase
):
    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_probe_forces_safe_runtime_even_when_ambient_env_is_live(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()
        captured = {}

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                env={
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "UNRELATED_SETTING":
                        "preserved",
                },
                runtime_opener=(
                    runtime_opener_for(
                        runtime,
                        captured=captured,
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.READY,
        )

        self.assertEqual(
            captured["env"][
                "STOCK_AGENT_RUNTIME_MODE"
            ],
            "safe",
        )

        self.assertEqual(
            captured["env"][
                "ROBINHOOD_LIVE_EXECUTION_ENABLED"
            ],
            "false",
        )

        self.assertEqual(
            captured["env"][
                "UNRELATED_SETTING"
            ],
            "preserved",
        )

        self.assertFalse(
            runtime.live_execution_enabled
        )

        self.assertIsNone(
            runtime.entry_placer
        )

        require_preflight.assert_called_once()

    def test_probe_rejects_runtime_that_is_live_enabled(
        self,
    ) -> None:
        runtime = make_runtime()

        runtime.live_execution_enabled = True

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpectedly enabled live execution",
        ):
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )

    def test_probe_rejects_runtime_that_exposes_entry_placer(
        self,
    ) -> None:
        runtime = make_runtime()

        runtime.entry_placer = object()

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpectedly exposed entry placer",
        ):
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_unresolved_exit_recovery_blocks_readiness(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        runtime.recovery = SimpleNamespace(
            has_unresolved_attempts=True,
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.BLOCKED,
        )

        self.assertFalse(
            result.exit_recovery_clear
        )

        self.assertIn(
            "unresolved exit placement recovery",
            result.blockers,
        )

        require_preflight.assert_called_once()

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_unresolved_entry_recovery_blocks_readiness(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        runtime.entry_recovery_service.recover.return_value = (
            SimpleNamespace(
                recovered=False,
            ),
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.BLOCKED,
        )

        self.assertFalse(
            result.entry_recovery_clear
        )

        self.assertFalse(
            result.activation_clear
        )

        self.assertFalse(
            result.preflight_clear
        )

        self.assertIn(
            "unresolved entry placement recovery",
            result.blockers,
        )

        runtime.entry_activation_reconciler.reconcile.assert_not_called()

        require_preflight.assert_not_called()

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_activation_failure_blocks_readiness(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        runtime.entry_activation_reconciler.reconcile.side_effect = (
            RuntimeError(
                "activation failed"
            )
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.BLOCKED,
        )

        self.assertTrue(
            result.entry_recovery_clear
        )

        self.assertFalse(
            result.activation_clear
        )

        self.assertFalse(
            result.preflight_clear
        )

        self.assertIn(
            "entry activation reconciliation failed",
            result.blockers,
        )

        require_preflight.assert_not_called()

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_preflight_failure_blocks_readiness(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        require_preflight.side_effect = (
            RuntimeError(
                "preflight unavailable"
            )
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.BLOCKED,
        )

        self.assertTrue(
            result.entry_recovery_clear
        )

        self.assertTrue(
            result.activation_clear
        )

        self.assertFalse(
            result.preflight_clear
        )

        self.assertIn(
            "live entry preflight failed",
            result.blockers,
        )

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_ten_dollars_already_reserved_blocks_another_five(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        runtime.entry_placement_journal.daily_reserved_notional.return_value = (
            Decimal("10")
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.BLOCKED,
        )

        self.assertFalse(
            result.daily_limit_clear
        )

        self.assertEqual(
            result.daily_reserved_notional,
            Decimal("10"),
        )

        self.assertIn(
            "daily live entry notional limit exhausted",
            result.blockers,
        )

        require_preflight.assert_called_once()

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_five_reserved_plus_five_requested_is_ready(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        runtime.entry_placement_journal.daily_reserved_notional.return_value = (
            Decimal("5")
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.READY,
        )

        self.assertTrue(
            result.ready
        )

        self.assertTrue(
            result.exit_recovery_clear
        )

        self.assertTrue(
            result.entry_recovery_clear
        )

        self.assertTrue(
            result.activation_clear
        )

        self.assertTrue(
            result.preflight_clear
        )

        self.assertTrue(
            result.daily_limit_clear
        )

        self.assertEqual(
            result.daily_reserved_notional,
            Decimal("5"),
        )

        self.assertEqual(
            result.requested_order_notional,
            Decimal("5"),
        )

        self.assertEqual(
            result.blockers,
            (),
        )

        self.assertEqual(
            result.preflight_blockers,
            (),
        )

        runtime.entry_recovery_service.recover.assert_called_once_with(
            account_number=(
                _ACCOUNT_NUMBER
            )
        )

        runtime.entry_activation_reconciler.reconcile.assert_called_once_with(
            account_number=(
                _ACCOUNT_NUMBER
            )
        )

        runtime.entry_placement_journal.daily_reserved_notional.assert_called_once_with(
            account_number=(
                _ACCOUNT_NUMBER
            ),
            as_of=(
                _EVALUATED_AT
            ),
        )

        require_preflight.assert_called_once()

    @patch(
        "stock_agent.orchestration."
        "robinhood_live_readiness."
        "require_live_equity_entry_preflight"
    )
    def test_preflight_blocker_is_preserved(
        self,
        require_preflight,
    ) -> None:
        runtime = make_runtime()

        require_preflight.side_effect = (
            EquityEntryPreflightBlockedError(
                EquityEntryPreflightResult(
                    blockers=(
                        EquityEntryPreflightBlocker
                        .OUTSIDE_ENTRY_WINDOW,
                    )
                )
            )
        )

        result = (
            check_robinhood_live_readiness(
                account_number=(
                    _ACCOUNT_NUMBER
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                not_found_grace_period=(
                    _GRACE_PERIOD
                ),
                requested_order_notional=(
                    Decimal("5")
                ),
                runtime_opener=(
                    runtime_opener_for(
                        runtime
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodLiveReadinessStatus.BLOCKED,
        )

        self.assertFalse(
            result.ready
        )

        self.assertTrue(
            result.exit_recovery_clear
        )

        self.assertTrue(
            result.entry_recovery_clear
        )

        self.assertTrue(
            result.activation_clear
        )

        self.assertFalse(
            result.preflight_clear
        )

        self.assertTrue(
            result.daily_limit_clear
        )

        self.assertEqual(
            result.preflight_blockers,
            (
                "outside_entry_window",
            ),
        )

        self.assertIn(
            "live entry preflight: "
            "outside_entry_window",
            result.blockers,
        )

        runtime.entry_recovery_service.recover.assert_called_once_with(
            account_number=(
                _ACCOUNT_NUMBER
            )
        )

        runtime.entry_activation_reconciler.reconcile.assert_called_once_with(
            account_number=(
                _ACCOUNT_NUMBER
            )
        )

        require_preflight.assert_called_once_with(
            runtime.entry_preflight_reader,
            account_number=(
                _ACCOUNT_NUMBER
            ),
            evaluated_at=(
                _EVALUATED_AT
            ),
            opening_debit=(
                Decimal("5")
            ),
            minimum_cash_reserve=(
                Decimal("5")
            ),
        )

        runtime.entry_placement_journal.daily_reserved_notional.assert_called_once_with(
            account_number=(
                _ACCOUNT_NUMBER
            ),
            as_of=(
                _EVALUATED_AT
            ),
        )


if __name__ == "__main__":
    unittest.main()