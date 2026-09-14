import unittest
from datetime import datetime, timedelta, timezone

from stock_agent.brokers.robinhood import (
    PlacementReconciliationReviewService,
    PlacementReconciliationStatus,
    ReconciliationReviewDecision,
    ReconciliationReviewPolicy,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementReconciliationObservationRecord,
)
from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationRequest,
)
from stock_agent.domain import AssetType


class FakeObservationJournal:
    def __init__(
        self,
        observations,
    ) -> None:
        self.observations = observations
        self.requested_ref_ids = []

    def list_reconciliation_observations(
        self,
        ref_id: str,
    ):
        self.requested_ref_ids.append(
            ref_id
        )

        return list(
            self.observations
        )

class PlacementReconciliationReviewServiceTests(
    unittest.TestCase
):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174001"
    )

    def make_request(
        self,
    ) -> PlacementReconciliationRequest:
        return PlacementReconciliationRequest(
            position_id="position-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            ref_id=self.REF_ID,
            placement_attempted_at=datetime(
                2026,
                9,
                12,
                2,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def test_returns_ready_after_required_not_found_observations(
        self,
    ) -> None:
        request = self.make_request()

        observations = [
            PlacementReconciliationObservationRecord(
                ref_id=self.REF_ID,
                status=(
                    PlacementReconciliationStatus.NOT_FOUND
                ),
                checked_at=datetime(
                    2026,
                    9,
                    12,
                    2,
                    10,
                    tzinfo=timezone.utc,
                ),
            ),
            PlacementReconciliationObservationRecord(
                ref_id=self.REF_ID,
                status=(
                    PlacementReconciliationStatus.NOT_FOUND
                ),
                checked_at=datetime(
                    2026,
                    9,
                    12,
                    2,
                    15,
                    tzinfo=timezone.utc,
                ),
            ),
        ]

        journal = FakeObservationJournal(
            observations
        )

        service = (
            PlacementReconciliationReviewService(
                journal,
                ReconciliationReviewPolicy(
                    min_not_found_observations=2,
                    min_observation_spacing=(
                        timedelta(minutes=5)
                    ),
                ),
            )
        )

        decision = service.evaluate(
            request
        )

        self.assertEqual(
            decision,
            ReconciliationReviewDecision
            .READY_FOR_MANUAL_REVIEW,
        )

        self.assertEqual(
            journal.requested_ref_ids,
            [
                self.REF_ID,
            ],
        )

    def test_waits_when_not_found_observations_are_insufficient(
        self,
    ) -> None:
        request = self.make_request()

        journal = FakeObservationJournal(
            [
                PlacementReconciliationObservationRecord(
                    ref_id=self.REF_ID,
                    status=(
                        PlacementReconciliationStatus
                        .NOT_FOUND
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        12,
                        2,
                        10,
                        tzinfo=timezone.utc,
                    ),
                ),
            ]
        )

        service = (
            PlacementReconciliationReviewService(
                journal,
                ReconciliationReviewPolicy(
                    min_not_found_observations=2,
                    min_observation_spacing=(
                        timedelta(minutes=5)
                    ),
                ),
            )
        )

        self.assertEqual(
            service.evaluate(request),
            ReconciliationReviewDecision
            .WAIT_FOR_OBSERVATION,
        )

    def test_still_unknown_breaks_not_found_streak(
        self,
    ) -> None:
        request = self.make_request()

        journal = FakeObservationJournal(
            [
                PlacementReconciliationObservationRecord(
                    ref_id=self.REF_ID,
                    status=(
                        PlacementReconciliationStatus
                        .NOT_FOUND
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        12,
                        2,
                        10,
                        tzinfo=timezone.utc,
                    ),
                ),
                PlacementReconciliationObservationRecord(
                    ref_id=self.REF_ID,
                    status=(
                        PlacementReconciliationStatus
                        .STILL_UNKNOWN
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        12,
                        2,
                        15,
                        tzinfo=timezone.utc,
                    ),
                ),
                PlacementReconciliationObservationRecord(
                    ref_id=self.REF_ID,
                    status=(
                        PlacementReconciliationStatus
                        .NOT_FOUND
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        12,
                        2,
                        20,
                        tzinfo=timezone.utc,
                    ),
                ),
            ]
        )

        service = (
            PlacementReconciliationReviewService(
                journal,
                ReconciliationReviewPolicy(
                    min_not_found_observations=2,
                    min_observation_spacing=(
                        timedelta(minutes=5)
                    ),
                ),
            )
        )

        self.assertEqual(
            service.evaluate(request),
            ReconciliationReviewDecision
            .WAIT_FOR_OBSERVATION,
        )

    def test_rejects_observation_for_different_request(
        self,
    ) -> None:
        request = self.make_request()

        journal = FakeObservationJournal(
            [
                PlacementReconciliationObservationRecord(
                    ref_id=(
                        "123e4567-e89b-12d3-a456-426614174999"
                    ),
                    status=(
                        PlacementReconciliationStatus
                        .NOT_FOUND
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        12,
                        2,
                        10,
                        tzinfo=timezone.utc,
                    ),
                ),
            ]
        )

        service = (
            PlacementReconciliationReviewService(
                journal,
                ReconciliationReviewPolicy(
                    min_not_found_observations=2,
                    min_observation_spacing=(
                        timedelta(minutes=5)
                    ),
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "ref_id does not match request",
        ):
            service.evaluate(
                request
            )