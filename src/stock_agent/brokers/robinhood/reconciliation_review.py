from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Sequence

from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationOutcome,
    PlacementReconciliationRequest,
    PlacementReconciliationStatus,
)


class ReconciliationReviewDecision(str, Enum):
    WAIT_FOR_OBSERVATION = "wait_for_observation"
    READY_FOR_MANUAL_REVIEW = "ready_for_manual_review"


@dataclass(frozen=True)
class ReconciliationReviewPolicy:
    min_not_found_observations: int
    min_observation_spacing: timedelta

    def __post_init__(self) -> None:
        if (
            type(self.min_not_found_observations) is not int
            or self.min_not_found_observations < 2
        ):
            raise ValueError(
                "min_not_found_observations must be at least 2"
            )

        if self.min_observation_spacing <= timedelta(0):
            raise ValueError(
                "min_observation_spacing must be positive"
            )

    def evaluate(
        self,
        request: PlacementReconciliationRequest,
        observations: Sequence[PlacementReconciliationOutcome],
    ) -> ReconciliationReviewDecision:
        counted = 0
        last_counted_at = None
        previous_checked_at = None

        for observation in observations:
            if observation.request != request:
                raise ValueError(
                    "reconciliation observation request mismatch"
                )

            if (
                previous_checked_at is not None
                and observation.checked_at <= previous_checked_at
            ):
                raise ValueError(
                    "reconciliation observations must be "
                    "strictly chronological"
                )

            previous_checked_at = observation.checked_at

            if (
                observation.status
                is not PlacementReconciliationStatus.NOT_FOUND
            ):
                # FOUND or STILL_UNKNOWN breaks the NOT_FOUND streak.
                counted = 0
                last_counted_at = None
                continue

            if (
                last_counted_at is None
                or observation.checked_at - last_counted_at
                >= self.min_observation_spacing
            ):
                counted += 1
                last_counted_at = observation.checked_at

        if counted >= self.min_not_found_observations:
            return (
                ReconciliationReviewDecision.READY_FOR_MANUAL_REVIEW
            )

        return ReconciliationReviewDecision.WAIT_FOR_OBSERVATION