import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood.closing_order_provenance import (
    ClosingOrderProvenanceError,
)
from stock_agent.brokers.robinhood.journal_position_close_service import (
    JournalBackedEquityPositionCloseService,
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
from stock_agent.orchestration.position_close_confirmation import (
    PositionCloseConfirmationError,
)


_NOW = datetime(
    2026,
    9,
    18,
    22,
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
    asset_type: AssetType = AssetType.EQUITY,
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

    action = (
        RobinhoodExitAction.EQUITY_SELL
        if asset_type is AssetType.EQUITY
        else RobinhoodExitAction.OPTION_SELL_TO_CLOSE
    )

    return PlacementAttemptRecord(
        submission=RobinhoodExitSubmission(
            request=RobinhoodExitOrderRequest(
                position_id=position_id,
                account_number="agentic-account",
                asset_type=asset_type,
                symbol="AAPL",
                quantity=Decimal("1"),
                action=action,
                option_id=(
                    None
                    if asset_type is AssetType.EQUITY
                    else "option-1"
                ),
            ),
            ref_id=ref_id,
            order_type=RobinhoodOrderType.MARKET,
        ),
        placement_attempted_at=_NOW,
        status=status,
        acknowledgement=acknowledgement,
        recovery_evidence=recovery_evidence,
    )


class FakePlacementJournal:
    def __init__(
        self,
        records: list[PlacementAttemptRecord],
    ) -> None:
        self.records = records
        self.list_resolved_call_count = 0

    def list_resolved(
        self,
    ) -> list[PlacementAttemptRecord]:
        self.list_resolved_call_count += 1
        return list(
            self.records
        )


class FakeCloseService:
    def __init__(
        self,
        *,
        result=None,
    ) -> None:
        self.result = result
        self.calls = []

    def confirm_if_filled(
        self,
        *,
        position_id: str,
        broker_order_id: str,
        ref_id: str,
    ):
        self.calls.append(
            (
                position_id,
                broker_order_id,
                ref_id,
            )
        )

        return self.result


class JournalBackedEquityPositionCloseServiceTests(
    unittest.TestCase
):
    def test_acknowledged_order_is_forwarded_to_close_service(
        self,
    ) -> None:
        record = make_record(
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            )
        )

        journal = FakePlacementJournal(
            [record]
        )

        close_service = FakeCloseService()

        service = (
            JournalBackedEquityPositionCloseService(
                journal,
                close_service,
            )
        )

        result = service.confirm_if_filled(
            position_id="position-1"
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            journal.list_resolved_call_count,
            1,
        )

        self.assertEqual(
            close_service.calls,
            [
                (
                    "position-1",
                    "broker-order-1",
                    record.submission.ref_id,
                )
            ],
        )

    def test_recovered_order_is_forwarded_to_close_service(
        self,
    ) -> None:
        record = make_record(
            status=(
                PlacementAttemptStatus
                .RECOVERED
            )
        )

        close_service = FakeCloseService()

        service = (
            JournalBackedEquityPositionCloseService(
                FakePlacementJournal(
                    [record]
                ),
                close_service,
            )
        )

        service.confirm_if_filled(
            position_id="position-1"
        )

        self.assertEqual(
            close_service.calls,
            [
                (
                    "position-1",
                    "broker-order-1",
                    record.submission.ref_id,
                )
            ],
        )

    def test_missing_provenance_does_not_call_close_service(
        self,
    ) -> None:
        close_service = FakeCloseService()

        service = (
            JournalBackedEquityPositionCloseService(
                FakePlacementJournal(
                    []
                ),
                close_service,
            )
        )

        result = service.confirm_if_filled(
            position_id="position-1"
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            close_service.calls,
            [],
        )

    def test_multiple_resolved_orders_are_rejected(
        self,
    ) -> None:
        first = make_record(
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            )
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

        close_service = FakeCloseService()

        service = (
            JournalBackedEquityPositionCloseService(
                FakePlacementJournal(
                    [
                        first,
                        second,
                    ]
                ),
                close_service,
            )
        )

        with self.assertRaisesRegex(
            ClosingOrderProvenanceError,
            "multiple resolved closing orders",
        ):
            service.confirm_if_filled(
                position_id="position-1"
            )

        self.assertEqual(
            close_service.calls,
            [],
        )

    def test_option_provenance_is_not_sent_to_equity_close_service(
        self,
    ) -> None:
        record = make_record(
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            ),
            asset_type=AssetType.OPTION,
        )

        close_service = FakeCloseService()

        service = (
            JournalBackedEquityPositionCloseService(
                FakePlacementJournal(
                    [record]
                ),
                close_service,
            )
        )

        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "requires equity closing-order provenance",
        ):
            service.confirm_if_filled(
                position_id="position-1"
            )

        self.assertEqual(
            close_service.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()