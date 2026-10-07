import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightBlocker,
    EquityEntryPreflightDataSource,
    EquityEntryPreflightDataUnavailableError,
    EquityEntryPreflightResult,
    EquityEntryPreflightSnapshot,
    evaluate_equity_entry_preflight,
)

from stock_agent.orchestration.equity_entry_preflight_service import (
    EquityEntryPreflightBlockedError,
    require_live_equity_entry_preflight,
)

_EVALUATED_AT = datetime(
    2026,
    10,
    5,
    18,
    0,
    tzinfo=timezone.utc,
)


class EquityEntryPreflightTests(
    unittest.TestCase
):
    def make_clean_snapshot(
        self,
    ) -> EquityEntryPreflightSnapshot:
        return EquityEntryPreflightSnapshot(
            has_existing_position=False,
            has_open_equity_order=False,
            has_open_option_order=False,
            has_opening_order_today=False,
            buying_power=Decimal("100"),
            cash=Decimal("100"),
        )

    def test_clean_snapshot_inside_entry_window_is_eligible(
        self,
    ) -> None:
        result = (
            evaluate_equity_entry_preflight(
                self.make_clean_snapshot(),
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertTrue(
            result.eligible
        )

        self.assertEqual(
            result.blockers,
            (),
        )

    def test_before_1015_et_is_blocked(
        self,
    ) -> None:
        result = (
            evaluate_equity_entry_preflight(
                self.make_clean_snapshot(),
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    14,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertIn(
            EquityEntryPreflightBlocker
            .OUTSIDE_ENTRY_WINDOW,
            result.blockers,
        )

    def test_existing_position_blocks_entry(
        self,
    ) -> None:
        snapshot = (
            EquityEntryPreflightSnapshot(
                has_existing_position=True,
                has_open_equity_order=False,
                has_open_option_order=False,
                has_opening_order_today=False,
                buying_power=Decimal("100"),
                cash=Decimal("100"),
            )
        )

        result = (
            evaluate_equity_entry_preflight(
                snapshot,
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertIn(
            EquityEntryPreflightBlocker
            .EXISTING_POSITION,
            result.blockers,
        )

    def test_open_order_blocks_entry(
        self,
    ) -> None:
        snapshot = (
            EquityEntryPreflightSnapshot(
                has_existing_position=False,
                has_open_equity_order=True,
                has_open_option_order=False,
                has_opening_order_today=False,
                buying_power=Decimal("100"),
                cash=Decimal("100"),
            )
        )

        result = (
            evaluate_equity_entry_preflight(
                snapshot,
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertFalse(
            result.eligible
        )

    def test_multiple_failures_are_all_reported(
        self,
    ) -> None:
        snapshot = (
            EquityEntryPreflightSnapshot(
                has_existing_position=True,
                has_open_equity_order=True,
                has_open_option_order=True,
                has_opening_order_today=True,
                buying_power=Decimal("9.99"),
                cash=Decimal("14.99"),
            )
        )

        result = (
            evaluate_equity_entry_preflight(
                snapshot,
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertEqual(
            set(result.blockers),
            {
                EquityEntryPreflightBlocker
                .EXISTING_POSITION,
                EquityEntryPreflightBlocker
                .OPEN_EQUITY_ORDER,
                EquityEntryPreflightBlocker
                .OPEN_OPTION_ORDER,
                EquityEntryPreflightBlocker
                .OPENING_ORDER_ALREADY_SUBMITTED_TODAY,
                EquityEntryPreflightBlocker
                .INSUFFICIENT_BUYING_POWER,
                EquityEntryPreflightBlocker
                .INSUFFICIENT_CASH_RESERVE,
            },
        )

    def test_buying_power_is_checked_against_opening_debit(
        self,
    ) -> None:
        snapshot = (
            EquityEntryPreflightSnapshot(
                has_existing_position=False,
                has_open_equity_order=False,
                has_open_option_order=False,
                has_opening_order_today=False,
                buying_power=Decimal("9.99"),
                cash=Decimal("100"),
            )
        )

        result = (
            evaluate_equity_entry_preflight(
                snapshot,
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertIn(
            EquityEntryPreflightBlocker
            .INSUFFICIENT_BUYING_POWER,
            result.blockers,
        )

    def test_cash_reserve_is_checked_after_opening_debit(
        self,
    ) -> None:
        snapshot = (
            EquityEntryPreflightSnapshot(
                has_existing_position=False,
                has_open_equity_order=False,
                has_open_option_order=False,
                has_opening_order_today=False,
                buying_power=Decimal("100"),
                cash=Decimal("14.99"),
            )
        )

        result = (
            evaluate_equity_entry_preflight(
                snapshot,
                evaluated_at=datetime(
                    2026,
                    9,
                    18,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ),
                opening_debit=Decimal("10"),
            )
        )

        self.assertIn(
            EquityEntryPreflightBlocker
            .INSUFFICIENT_CASH_RESERVE,
            result.blockers,
        )

    def test_preserves_unavailable_data_source(
        self,
    ) -> None:
        class Reader:
            def read(
                self,
                *,
                account_number,
                evaluated_at,
            ):
                raise (
                    EquityEntryPreflightDataUnavailableError(
                        EquityEntryPreflightDataSource
                        .FUNDS,
                        RuntimeError(
                            "funds unavailable"
                        ),
                    )
                )

        with self.assertRaises(
            EquityEntryPreflightBlockedError
        ) as context:
            require_live_equity_entry_preflight(
                Reader(),
                account_number=(
                    "agentic-account"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                opening_debit=(
                    Decimal("5")
                ),
            )

        self.assertEqual(
            context.exception.result.blockers,
            (
                EquityEntryPreflightBlocker
                .DATA_UNAVAILABLE,
            ),
        )

        self.assertEqual(
            context.exception
            .result
            .unavailable_sources,
            (
                EquityEntryPreflightDataSource
                .FUNDS,
            ),
        )