import tempfile
import unittest

from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.entry_execution_limits import (
    EquityEntryDailyLimitExceededError,
)
from stock_agent.brokers.robinhood.entry_placement import (
    EntryPlacementStatus,
    EquityEntryPlacementRecord,
    SQLiteEquityEntryPlacementJournal,
)


def record(
    ref_id: str,
    *,
    account_number: str = "account-1",
    amount: str = "5",
    attempted_at: datetime,
    status: EntryPlacementStatus = (
        EntryPlacementStatus.PREPARED
    ),
) -> EquityEntryPlacementRecord:
    return EquityEntryPlacementRecord(
        ref_id=ref_id,
        account_number=account_number,
        symbol="AAPL",
        arguments={
            "account_number":
                account_number,
            "symbol": "AAPL",
            "side": "buy",
            "time_in_force": "gfd",
            "market_hours":
                "regular_hours",
            "type": "market",
            "dollar_amount": amount,
            "ref_id": ref_id,
        },
        attempted_at=attempted_at,
        status=status,
    )


class EquityEntryDailyLimitTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.tempdir = (
            tempfile.TemporaryDirectory()
        )

        database_path = (
            Path(
                self.tempdir.name
            )
            / "entries.sqlite3"
        )

        self.journal = (
            SQLiteEquityEntryPlacementJournal(
                database_path
            )
        )

        self.journal.initialize()

    def tearDown(
        self,
    ) -> None:
        self.tempdir.cleanup()

    def test_first_five_dollar_reservation_is_allowed(
        self,
    ) -> None:
        attempted_at = datetime(
            2026,
            10,
            5,
            18,
            0,
            tzinfo=timezone.utc,
        )

        total = (
            self.journal
            .reserve_prepared_with_daily_limit(
                record(
                    "entry-1",
                    attempted_at=(
                        attempted_at
                    ),
                )
            )
        )

        self.assertEqual(
            total,
            Decimal("5"),
        )

        stored = self.journal.get(
            "entry-1"
        )

        self.assertIsNotNone(
            stored
        )

        self.assertEqual(
            stored.status,
            EntryPlacementStatus.PREPARED,
        )

    def test_second_five_dollar_reservation_reaches_daily_limit(
        self,
    ) -> None:
        attempted_at = datetime(
            2026,
            10,
            5,
            18,
            0,
            tzinfo=timezone.utc,
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "entry-1",
                attempted_at=attempted_at,
            )
        )

        total = (
            self.journal
            .reserve_prepared_with_daily_limit(
                record(
                    "entry-2",
                    attempted_at=(
                        attempted_at
                    ),
                )
            )
        )

        self.assertEqual(
            total,
            Decimal("10"),
        )

    def test_third_five_dollar_reservation_is_blocked(
        self,
    ) -> None:
        attempted_at = datetime(
            2026,
            10,
            5,
            18,
            0,
            tzinfo=timezone.utc,
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "entry-1",
                attempted_at=attempted_at,
            )
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "entry-2",
                attempted_at=attempted_at,
            )
        )

        with self.assertRaises(
            EquityEntryDailyLimitExceededError
        ):
            self.journal.reserve_prepared_with_daily_limit(
                record(
                    "entry-3",
                    attempted_at=(
                        attempted_at
                    ),
                )
            )

        self.assertIsNone(
            self.journal.get(
                "entry-3"
            )
        )

    def test_previous_trading_day_does_not_count(
        self,
    ) -> None:
        previous_day = datetime(
            2026,
            10,
            2,
            18,
            0,
            tzinfo=timezone.utc,
        )

        current_day = datetime(
            2026,
            10,
            5,
            18,
            0,
            tzinfo=timezone.utc,
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "old-entry-1",
                attempted_at=(
                    previous_day
                ),
            )
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "old-entry-2",
                attempted_at=(
                    previous_day
                ),
            )
        )

        total = (
            self.journal
            .reserve_prepared_with_daily_limit(
                record(
                    "new-entry",
                    attempted_at=(
                        current_day
                    ),
                )
            )
        )

        self.assertEqual(
            total,
            Decimal("5"),
        )

    def test_other_account_does_not_count(
        self,
    ) -> None:
        attempted_at = datetime(
            2026,
            10,
            5,
            18,
            0,
            tzinfo=timezone.utc,
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "other-1",
                account_number=(
                    "account-2"
                ),
                attempted_at=(
                    attempted_at
                ),
            )
        )

        self.journal.reserve_prepared_with_daily_limit(
            record(
                "other-2",
                account_number=(
                    "account-2"
                ),
                attempted_at=(
                    attempted_at
                ),
            )
        )

        total = (
            self.journal
            .reserve_prepared_with_daily_limit(
                record(
                    "mine-1",
                    account_number=(
                        "account-1"
                    ),
                    attempted_at=(
                        attempted_at
                    ),
                )
            )
        )

        self.assertEqual(
            total,
            Decimal("5"),
        )


if __name__ == "__main__":
    unittest.main()