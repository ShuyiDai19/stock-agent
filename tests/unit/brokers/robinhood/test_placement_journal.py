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
    PlacementAcknowledgement,
    PlacementAttemptStateConflictError,
    PlacementAttemptStatus,
)
from stock_agent.domain import AssetType


class SQLitePlacementAttemptJournalTests(unittest.TestCase):
    PREPARED_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174001"
    )
    SUBMITTING_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174002"
    )
    UNCERTAIN_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174003"
    )
    NOT_SENT_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174004"
    )
    ACKNOWLEDGED_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174005"
    )
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

    def make_equity_record(
        self,
        *,
        ref_id: str | None = None,
        attempted_at: datetime | None = None,
    ) -> PlacementAttemptRecord:
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
            ref_id=ref_id or self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

        return PlacementAttemptRecord(
            submission=submission,
            placement_attempted_at=(
                attempted_at or self.ATTEMPTED_AT
            ),
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

    def test_acknowledges_submitting_attempt_atomically(
        self,
    ) -> None:
        record = self.make_equity_record()

        self.journal.insert(record)

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        acknowledgement = PlacementAcknowledgement(
            broker_order_id="broker-order-123",
            acknowledged_at=datetime(
                2026,
                9,
                2,
                4,
                51,
                tzinfo=timezone.utc,
            ),
        )

        self.journal.acknowledge(
            self.REF_ID,
            acknowledgement,
        )

        reopened = SQLitePlacementAttemptJournal(
            self.database_path
        )

        persisted = reopened.get(
            self.REF_ID
        )

        self.assertEqual(
            persisted.status,
            PlacementAttemptStatus.ACKNOWLEDGED,
        )

        self.assertEqual(
            persisted.acknowledgement,
            acknowledgement,
        )

    def test_cannot_acknowledge_prepared_attempt(
        self,
    ) -> None:
        self.journal.insert(
            self.make_equity_record()
        )

        acknowledgement = PlacementAcknowledgement(
            broker_order_id="broker-order-123",
            acknowledged_at=datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaises(
            PlacementAttemptStateConflictError
        ):
            self.journal.acknowledge(
                self.REF_ID,
                acknowledgement,
            )

        persisted = self.journal.get(
            self.REF_ID
        )

        self.assertEqual(
            persisted.status,
            PlacementAttemptStatus.PREPARED,
        )

        self.assertIsNone(
            persisted.acknowledgement,
        )

    def test_acknowledged_record_requires_acknowledgement(
        self,
    ) -> None:
        record = self.make_equity_record()

        with self.assertRaisesRegex(
            ValueError,
            "acknowledged placement requires acknowledgement",
        ):
            PlacementAttemptRecord(
                submission=record.submission,
                placement_attempted_at=(
                    record.placement_attempted_at
                ),
                status=(
                    PlacementAttemptStatus.ACKNOWLEDGED
                ),
            )

    def test_non_acknowledged_record_rejects_acknowledgement(
        self,
    ) -> None:
        record = self.make_equity_record()

        acknowledgement = PlacementAcknowledgement(
            broker_order_id="broker-order-123",
            acknowledged_at=datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            (
                "non-acknowledged placement cannot contain "
                "acknowledgement"
            ),
        ):
            PlacementAttemptRecord(
                submission=record.submission,
                placement_attempted_at=(
                    record.placement_attempted_at
                ),
                status=PlacementAttemptStatus.SUBMITTING,
                acknowledgement=acknowledgement,
            )

    def test_cannot_acknowledge_twice(
        self,
    ) -> None:
        self.journal.insert(
            self.make_equity_record()
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        acknowledgement = PlacementAcknowledgement(
            broker_order_id="broker-order-123",
            acknowledged_at=datetime.now(
                timezone.utc
            ),
        )

        self.journal.acknowledge(
            self.REF_ID,
            acknowledgement,
        )

        with self.assertRaises(
            PlacementAttemptStateConflictError
        ):
            self.journal.acknowledge(
                self.REF_ID,
                acknowledgement,
            )

    def test_submitting_attempt_can_be_marked_not_sent(
        self,
    ) -> None:
        self.journal.insert(
            self.make_equity_record()
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.SUBMITTING,
            new_status=PlacementAttemptStatus.NOT_SENT,
        )

        persisted = self.journal.get(
            self.REF_ID
        )

        self.assertEqual(
            persisted.status,
            PlacementAttemptStatus.NOT_SENT,
        )

        self.assertIsNone(
            persisted.acknowledgement,
        )

    def test_not_sent_cannot_return_to_submitting(
        self,
    ) -> None:
        self.journal.insert(
            self.make_equity_record()
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.SUBMITTING,
            new_status=PlacementAttemptStatus.NOT_SENT,
        )

        with self.assertRaisesRegex(
            ValueError,
            "invalid placement attempt state transition",
        ):
            self.journal.transition(
                self.REF_ID,
                expected_status=PlacementAttemptStatus.NOT_SENT,
                new_status=PlacementAttemptStatus.SUBMITTING,
            )

        self.assertEqual(
            self.journal.get(self.REF_ID).status,
            PlacementAttemptStatus.NOT_SENT,
        )

    def test_not_sent_attempt_cannot_be_acknowledged(
        self,
    ) -> None:
        self.journal.insert(
            self.make_equity_record()
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.transition(
            self.REF_ID,
            expected_status=PlacementAttemptStatus.SUBMITTING,
            new_status=PlacementAttemptStatus.NOT_SENT,
        )

        acknowledgement = PlacementAcknowledgement(
            broker_order_id="broker-order-123",
            acknowledged_at=datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaises(
            PlacementAttemptStateConflictError
        ):
            self.journal.acknowledge(
                self.REF_ID,
                acknowledgement,
            )

        persisted = self.journal.get(
            self.REF_ID
        )

        self.assertEqual(
            persisted.status,
            PlacementAttemptStatus.NOT_SENT,
        )

        self.assertIsNone(
            persisted.acknowledgement,
        )

    def test_lists_only_unresolved_attempts(
        self,
    ) -> None:
        prepared = self.make_equity_record(
            ref_id=self.PREPARED_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                40,
                tzinfo=timezone.utc,
            ),
        )

        submitting = self.make_equity_record(
            ref_id=self.SUBMITTING_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                41,
                tzinfo=timezone.utc,
            ),
        )

        uncertain = self.make_equity_record(
            ref_id=self.UNCERTAIN_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                42,
                tzinfo=timezone.utc,
            ),
        )

        not_sent = self.make_equity_record(
            ref_id=self.NOT_SENT_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                43,
                tzinfo=timezone.utc,
            ),
        )

        acknowledged = self.make_equity_record(
            ref_id=self.ACKNOWLEDGED_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                44,
                tzinfo=timezone.utc,
            ),
        )

        for record in (
            prepared,
            submitting,
            uncertain,
            not_sent,
            acknowledged,
        ):
            self.journal.insert(record)

        self.journal.transition(
            submitting.submission.ref_id,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.transition(
            uncertain.submission.ref_id,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.transition(
            uncertain.submission.ref_id,
            expected_status=PlacementAttemptStatus.SUBMITTING,
            new_status=PlacementAttemptStatus.UNCERTAIN,
        )

        self.journal.transition(
            not_sent.submission.ref_id,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.transition(
            not_sent.submission.ref_id,
            expected_status=PlacementAttemptStatus.SUBMITTING,
            new_status=PlacementAttemptStatus.NOT_SENT,
        )

        self.journal.transition(
            acknowledged.submission.ref_id,
            expected_status=PlacementAttemptStatus.PREPARED,
            new_status=PlacementAttemptStatus.SUBMITTING,
        )

        self.journal.acknowledge(
            acknowledged.submission.ref_id,
            PlacementAcknowledgement(
                broker_order_id="broker-order-123",
                acknowledged_at=datetime(
                    2026,
                    9,
                    2,
                    4,
                    45,
                    tzinfo=timezone.utc,
                ),
            ),
        )

        unresolved = (
            self.journal.list_unresolved()
        )

        self.assertEqual(
            [
                record.status
                for record in unresolved
            ],
            [
                PlacementAttemptStatus.PREPARED,
                PlacementAttemptStatus.SUBMITTING,
                PlacementAttemptStatus.UNCERTAIN,
            ],
        )

        self.assertEqual(
            [
                record.submission.ref_id
                for record in unresolved
            ],
            [
                self.PREPARED_REF_ID,
                self.SUBMITTING_REF_ID,
                self.UNCERTAIN_REF_ID,
            ],
        )

    def test_lists_unresolved_attempts_oldest_first(
        self,
    ) -> None:
        later = self.make_equity_record(
            ref_id=self.SUBMITTING_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                50,
                tzinfo=timezone.utc,
            ),
        )

        earlier = self.make_equity_record(
            ref_id=self.PREPARED_REF_ID,
            attempted_at=datetime(
                2026,
                9,
                2,
                4,
                40,
                tzinfo=timezone.utc,
            ),
        )

        # Insert deliberately out of order.
        self.journal.insert(later)
        self.journal.insert(earlier)

        unresolved = (
            self.journal.list_unresolved()
        )

        self.assertEqual(
            [
                record.submission.ref_id
                for record in unresolved
            ],
            [
                self.PREPARED_REF_ID,
                self.SUBMITTING_REF_ID,
            ],
        )

    def test_list_unresolved_returns_empty_list(
        self,
    ) -> None:
        self.assertEqual(
            self.journal.list_unresolved(),
            [],
        )

if __name__ == "__main__":
    unittest.main()