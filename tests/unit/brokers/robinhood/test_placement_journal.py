import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptAlreadyExistsError,
    PlacementAttemptRecord,
    SQLitePlacementAttemptJournal,
    PlacementAttemptStateConflictError,
    PlacementAttemptStatus,
)
from stock_agent.domain import AssetType


class SQLitePlacementAttemptJournalTests(unittest.TestCase):
    REF_ID = "123e4567-e89b-12d3-a456-426614174000"
    ATTEMPTED_AT = datetime(
        2026, 9, 2, 4, 50, tzinfo=timezone.utc
    )

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.database_path = (
            Path(self.temp_dir.name) / "placement.sqlite3"
        )
        self.journal = SQLitePlacementAttemptJournal(
            self.database_path
        )
        self.journal.initialize()

    def make_equity_record(self) -> PlacementAttemptRecord:
        submission = RobinhoodExitSubmission(
            request=RobinhoodExitOrderRequest(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("0.031"),
                action=RobinhoodExitAction.EQUITY_SELL,
                option_id=None,
            ),
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )
        return PlacementAttemptRecord(
            submission=submission,
            placement_attempted_at=self.ATTEMPTED_AT,
        )

    def test_persists_exact_submission_across_reopen(self) -> None:
        record = self.make_equity_record()
        self.journal.insert(record)

        reopened = SQLitePlacementAttemptJournal(
            self.database_path
        )
        reopened.initialize()

        self.assertEqual(
            reopened.get(self.REF_ID),
            record,
        )

    def test_rejects_duplicate_ref_id_without_overwriting(self) -> None:
        record = self.make_equity_record()
        self.journal.insert(record)

        modified = replace(
            record,
            submission=replace(
                record.submission,
                request=replace(
                    record.submission.request,
                    quantity=Decimal("0.032"),
                ),
            ),
        )

        with self.assertRaises(
            PlacementAttemptAlreadyExistsError
        ):
            self.journal.insert(modified)

        self.assertEqual(
            self.journal.get(self.REF_ID),
            record,
        )

    def test_rejects_naive_attempt_timestamp(self) -> None:
        record = self.make_equity_record()

        with self.assertRaisesRegex(
            ValueError,
            "placement_attempted_at must be timezone-aware",
        ):
            replace(
                record,
                placement_attempted_at=datetime(
                    2026, 9, 2, 4, 50
                ),
            )

        self.assertIsNone(
            self.journal.get(self.REF_ID)
        )

    def test_missing_ref_id_returns_none(self) -> None:
        self.assertIsNone(
            self.journal.get("unknown-ref-id")
        )

    def test_persists_submitting_status_across_reopen(
        self,
    ) -> None:
        record = self.make_equity_record()
        self.journal.insert(record)

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        reopened = SQLitePlacementAttemptJournal(
            self.database_path
        )

        self.assertEqual(
            reopened.get(self.REF_ID).status,
            PlacementAttemptStatus.SUBMITTING,
        )


    def test_prepared_attempt_can_be_marked_uncertain(
        self,
    ) -> None:
        self.journal.insert(self.make_equity_record())

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.UNCERTAIN,
        )

        self.assertEqual(
            self.journal.get(self.REF_ID).status,
            PlacementAttemptStatus.UNCERTAIN,
        )


    def test_rejects_stale_state_transition(
        self,
    ) -> None:
        self.journal.insert(self.make_equity_record())

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        with self.assertRaises(
            PlacementAttemptStateConflictError
        ):
            self.journal.transition(
                self.REF_ID,
                expected_status=PlacementAttemptStatus.PREPARED,
                new_status=PlacementAttemptStatus.SUBMITTING,
            )

        self.assertEqual(
            self.journal.get(self.REF_ID).status,
            PlacementAttemptStatus.SUBMITTING,
        )


    def test_uncertain_cannot_return_to_submitting(
        self,
    ) -> None:
        self.journal.insert(self.make_equity_record())

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.UNCERTAIN,
        )

        with self.assertRaisesRegex(
            ValueError,
            "invalid placement attempt state transition",
        ):
            self.journal.transition(
                self.REF_ID,
                expected_status=PlacementAttemptStatus.UNCERTAIN,
                new_status=PlacementAttemptStatus.SUBMITTING,
            )

        self.assertEqual(
            self.journal.get(self.REF_ID).status,
            PlacementAttemptStatus.UNCERTAIN,
        )


if __name__ == "__main__":
    unittest.main()