import unittest
from datetime import datetime, timedelta, timezone

from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationOutcome,
    PlacementReconciliationRequest,
    PlacementReconciliationStatus,
)
from stock_agent.brokers.robinhood.reconciliation_review import (
    ReconciliationReviewDecision,
    ReconciliationReviewPolicy,
)
from stock_agent.domain import AssetType


class ReconciliationReviewPolicyTests(unittest.TestCase):
    T0 = datetime(2026, 9, 2, 4, 40, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self.request = PlacementReconciliationRequest(
            position_id="position-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            ref_id="123e4567-e89b-12d3-a456-426614174000",
            placement_attempted_at=self.T0,
        )
        self.policy = ReconciliationReviewPolicy(
            min_not_found_observations=2,
            min_observation_spacing=timedelta(seconds=30),
        )

    def observation(
        self,
        status: PlacementReconciliationStatus,
        seconds: int,
    ) -> PlacementReconciliationOutcome:
        return PlacementReconciliationOutcome(
            request=self.request,
            status=status,
            checked_at=self.T0 + timedelta(seconds=seconds),
            broker_order_id=(
                "broker-order-123"
                if status is PlacementReconciliationStatus.FOUND
                else None
            ),
        )

    def test_one_not_found_is_not_enough(self) -> None:
        decision = self.policy.evaluate(
            self.request,
            [self.observation(
                PlacementReconciliationStatus.NOT_FOUND, 60
            )],
        )
        self.assertEqual(
            decision,
            ReconciliationReviewDecision.WAIT_FOR_OBSERVATION,
        )

    def test_two_spaced_not_found_observations_allow_review(self) -> None:
        decision = self.policy.evaluate(
            self.request,
            [
                self.observation(
                    PlacementReconciliationStatus.NOT_FOUND, 60
                ),
                self.observation(
                    PlacementReconciliationStatus.NOT_FOUND, 90
                ),
            ],
        )
        self.assertEqual(
            decision,
            ReconciliationReviewDecision.READY_FOR_MANUAL_REVIEW,
        )

    def test_observations_too_close_do_not_count_twice(self) -> None:
        decision = self.policy.evaluate(
            self.request,
            [
                self.observation(
                    PlacementReconciliationStatus.NOT_FOUND, 60
                ),
                self.observation(
                    PlacementReconciliationStatus.NOT_FOUND, 65
                ),
            ],
        )
        self.assertEqual(
            decision,
            ReconciliationReviewDecision.WAIT_FOR_OBSERVATION,
        )

    def test_unknown_breaks_not_found_streak(self) -> None:
        decision = self.policy.evaluate(
            self.request,
            [
                self.observation(
                    PlacementReconciliationStatus.NOT_FOUND, 60
                ),
                self.observation(
                    PlacementReconciliationStatus.STILL_UNKNOWN, 90
                ),
                self.observation(
                    PlacementReconciliationStatus.NOT_FOUND, 120
                ),
            ],
        )
        self.assertEqual(
            decision,
            ReconciliationReviewDecision.WAIT_FOR_OBSERVATION,
        )

    def test_rejects_duplicate_observation_timestamp(self) -> None:
        observations = [
            self.observation(
                PlacementReconciliationStatus.NOT_FOUND, 60
            ),
            self.observation(
                PlacementReconciliationStatus.NOT_FOUND, 60
            ),
        ]
        with self.assertRaisesRegex(
            ValueError, "strictly chronological"
        ):
            self.policy.evaluate(self.request, observations)

    def test_rejects_single_observation_policy(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 2"):
            ReconciliationReviewPolicy(
                min_not_found_observations=1,
                min_observation_spacing=timedelta(seconds=30),
            )


if __name__ == "__main__":
    unittest.main()