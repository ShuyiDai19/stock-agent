import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAcknowledgement,
    PlacementAttemptRecord,
    PlacementAttemptStatus,
    PlacementRecoveryEvidence,
    SQLitePlacementAttemptJournal,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType


def make_record(
    *,
    ref_id: str,
    position_id: str,
    attempted_at: datetime,
) -> PlacementAttemptRecord:
    return PlacementAttemptRecord(
        submission=RobinhoodExitSubmission(
            request=RobinhoodExitOrderRequest(
                position_id=position_id,
                account_number="agentic-account",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("1"),
                action=(
                    RobinhoodExitAction
                    .EQUITY_SELL
                ),
                option_id=None,
            ),
            ref_id=ref_id,
            order_type=RobinhoodOrderType.MARKET,
        ),
        placement_attempted_at=attempted_at,
    )


class SQLitePlacementAttemptJournalResolvedTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        self.journal = (
            SQLitePlacementAttemptJournal(
                Path(
                    self.temp_directory.name
                )
                / "placement.sqlite3"
            )
        )

        self.journal.initialize()

    def tearDown(
        self,
    ) -> None:
        self.temp_directory.cleanup()

    def test_list_resolved_returns_acknowledged_and_recovered_only(
        self,
    ) -> None:
        recovered = make_record(
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
            position_id="position-1",
            attempted_at=datetime(
                2026,
                9,
                18,
                20,
                0,
                tzinfo=timezone.utc,
            ),
        )

        acknowledged = make_record(
            ref_id=(
                "00000000-0000-4000-8000-000000000002"
            ),
            position_id="position-2",
            attempted_at=datetime(
                2026,
                9,
                18,
                20,
                1,
                tzinfo=timezone.utc,
            ),
        )

        unresolved = make_record(
            ref_id=(
                "00000000-0000-4000-8000-000000000003"
            ),
            position_id="position-3",
            attempted_at=datetime(
                2026,
                9,
                18,
                20,
                2,
                tzinfo=timezone.utc,
            ),
        )

        self.journal.insert(
            recovered
        )

        self.journal.recover_found(
            recovered.submission.ref_id,
            PlacementRecoveryEvidence(
                broker_order_id=(
                    "broker-order-recovered"
                ),
                recovered_at=datetime(
                    2026,
                    9,
                    18,
                    20,
                    5,
                    tzinfo=timezone.utc,
                ),
            ),
        )

        self.journal.insert(
            acknowledged
        )

        self.journal.transition(
            acknowledged.submission.ref_id,
            expected_status=(
                PlacementAttemptStatus.PREPARED
            ),
            new_status=(
                PlacementAttemptStatus.SUBMITTING
            ),
        )

        self.journal.acknowledge(
            acknowledged.submission.ref_id,
            PlacementAcknowledgement(
                broker_order_id=(
                    "broker-order-acknowledged"
                ),
                acknowledged_at=datetime(
                    2026,
                    9,
                    18,
                    20,
                    6,
                    tzinfo=timezone.utc,
                ),
            ),
        )

        self.journal.insert(
            unresolved
        )

        records = (
            self.journal.list_resolved()
        )

        self.assertEqual(
            len(records),
            2,
        )

        self.assertEqual(
            [
                record.status
                for record in records
            ],
            [
                PlacementAttemptStatus.RECOVERED,
                PlacementAttemptStatus.ACKNOWLEDGED,
            ],
        )

        self.assertEqual(
            [
                record.submission.ref_id
                for record in records
            ],
            [
                recovered.submission.ref_id,
                acknowledged.submission.ref_id,
            ],
        )

        self.assertEqual(
            (
                records[0]
                .recovery_evidence
                .broker_order_id
            ),
            "broker-order-recovered",
        )

        self.assertEqual(
            (
                records[1]
                .acknowledgement
                .broker_order_id
            ),
            "broker-order-acknowledged",
        )

    def test_list_resolved_returns_empty_list_when_none_exist(
        self,
    ) -> None:
        record = make_record(
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
            position_id="position-1",
            attempted_at=datetime(
                2026,
                9,
                18,
                20,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.journal.insert(
            record
        )

        self.assertEqual(
            self.journal.list_resolved(),
            [],
        )


if __name__ == "__main__":
    unittest.main()