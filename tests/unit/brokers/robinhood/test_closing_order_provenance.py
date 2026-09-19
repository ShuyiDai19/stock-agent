import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood.closing_order_provenance import (
    ClosingOrderProvenanceError,
    build_closing_order_provenance,
    resolve_closing_order_provenance,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAcknowledgement,
    PlacementAttemptRecord,
    PlacementAttemptStatus,
    PlacementRecoveryEvidence,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType


_NOW = datetime(
    2026,
    9,
    18,
    20,
    0,
    tzinfo=timezone.utc,
)


def make_record(
    *,
    status: PlacementAttemptStatus,
    position_id: str = "position-1",
    ref_id: str = (
        "00000000-0000-4000-8000-000000000001"
    ),
    broker_order_id: str = "broker-order-1",
) -> PlacementAttemptRecord:
    acknowledgement = None
    recovery_evidence = None

    if (
        status
        is PlacementAttemptStatus.ACKNOWLEDGED
    ):
        acknowledgement = (
            PlacementAcknowledgement(
                broker_order_id=broker_order_id,
                acknowledged_at=_NOW,
            )
        )

    if (
        status
        is PlacementAttemptStatus.RECOVERED
    ):
        recovery_evidence = (
            PlacementRecoveryEvidence(
                broker_order_id=broker_order_id,
                recovered_at=_NOW,
            )
        )

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
        placement_attempted_at=_NOW,
        status=status,
        acknowledgement=acknowledgement,
        recovery_evidence=recovery_evidence,
    )


class ClosingOrderProvenanceTests(
    unittest.TestCase
):
    def test_acknowledged_record_builds_provenance(
        self,
    ) -> None:
        record = make_record(
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            ),
        )

        provenance = (
            build_closing_order_provenance(
                record
            )
        )

        self.assertIsNotNone(
            provenance
        )

        self.assertEqual(
            provenance.position_id,
            "position-1",
        )

        self.assertEqual(
            provenance.ref_id,
            record.submission.ref_id,
        )

        self.assertEqual(
            provenance.broker_order_id,
            "broker-order-1",
        )

    def test_recovered_record_builds_provenance(
        self,
    ) -> None:
        record = make_record(
            status=(
                PlacementAttemptStatus
                .RECOVERED
            ),
        )

        provenance = (
            build_closing_order_provenance(
                record
            )
        )

        self.assertIsNotNone(
            provenance
        )

        self.assertEqual(
            provenance.broker_order_id,
            "broker-order-1",
        )

        self.assertEqual(
            provenance.ref_id,
            record.submission.ref_id,
        )

    def test_unresolved_records_do_not_provide_provenance(
        self,
    ) -> None:
        for status in (
            PlacementAttemptStatus.PREPARED,
            PlacementAttemptStatus.SUBMITTING,
            PlacementAttemptStatus.UNCERTAIN,
            PlacementAttemptStatus.NOT_SENT,
        ):
            with self.subTest(
                status=status
            ):
                provenance = (
                    build_closing_order_provenance(
                        make_record(
                            status=status
                        )
                    )
                )

                self.assertIsNone(
                    provenance
                )

    def test_resolver_returns_matching_position(
        self,
    ) -> None:
        other = make_record(
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            ),
            position_id="position-2",
            ref_id=(
                "00000000-0000-4000-8000-000000000002"
            ),
            broker_order_id="broker-order-2",
        )

        matching = make_record(
            status=(
                PlacementAttemptStatus
                .RECOVERED
            ),
        )

        provenance = (
            resolve_closing_order_provenance(
                [
                    other,
                    matching,
                ],
                position_id="position-1",
            )
        )

        self.assertIsNotNone(
            provenance
        )

        self.assertEqual(
            provenance.position_id,
            "position-1",
        )

        self.assertEqual(
            provenance.broker_order_id,
            "broker-order-1",
        )

    def test_resolver_returns_none_without_resolved_match(
        self,
    ) -> None:
        record = make_record(
            status=(
                PlacementAttemptStatus
                .UNCERTAIN
            ),
        )

        provenance = (
            resolve_closing_order_provenance(
                [record],
                position_id="position-1",
            )
        )

        self.assertIsNone(
            provenance
        )

    def test_multiple_resolved_orders_for_position_are_rejected(
        self,
    ) -> None:
        first = make_record(
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            ),
        )

        second = make_record(
            status=(
                PlacementAttemptStatus
                .RECOVERED
            ),
            ref_id=(
                "00000000-0000-4000-8000-000000000002"
            ),
            broker_order_id="broker-order-2",
        )

        with self.assertRaisesRegex(
            ClosingOrderProvenanceError,
            "multiple resolved closing orders",
        ):
            resolve_closing_order_provenance(
                [
                    first,
                    second,
                ],
                position_id="position-1",
            )


if __name__ == "__main__":
    unittest.main()