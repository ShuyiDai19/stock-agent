from dataclasses import dataclass
from enum import Enum

from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptRecord,
    PlacementAttemptStatus,
)


class PlacementRecoveryAction(str, Enum):
    RECONCILE = "reconcile"
    FRESH_REVIEW_REQUIRED = "fresh_review_required"
    NO_ACTION = "no_action"


@dataclass(frozen=True)
class PlacementRecoveryPlan:
    record: PlacementAttemptRecord
    action: PlacementRecoveryAction


class PlacementRecoveryPlanner:
    def plan(
        self,
        record: PlacementAttemptRecord,
    ) -> PlacementRecoveryPlan:
        status = record.status

        if status in {
            PlacementAttemptStatus.PREPARED,
            PlacementAttemptStatus.SUBMITTING,
            PlacementAttemptStatus.UNCERTAIN,
        }:
            return PlacementRecoveryPlan(
                record=record,
                action=PlacementRecoveryAction.RECONCILE,
            )

        if status is PlacementAttemptStatus.NOT_SENT:
            return PlacementRecoveryPlan(
                record=record,
                action=(
                    PlacementRecoveryAction.FRESH_REVIEW_REQUIRED
                ),
            )

        if status is PlacementAttemptStatus.ACKNOWLEDGED:
            return PlacementRecoveryPlan(
                record=record,
                action=PlacementRecoveryAction.NO_ACTION,
            )

        raise ValueError(
            f"unsupported placement attempt status: {status}"
        )