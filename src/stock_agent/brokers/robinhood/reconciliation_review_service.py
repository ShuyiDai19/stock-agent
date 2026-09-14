from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptJournal,
    PlacementReconciliationObservationRecord,
)
from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationOutcome,
    PlacementReconciliationRequest,
)
from stock_agent.brokers.robinhood.reconciliation_review import (
    ReconciliationReviewDecision,
    ReconciliationReviewPolicy,
)


def restore_reconciliation_outcome(
    request: PlacementReconciliationRequest,
    observation: PlacementReconciliationObservationRecord,
) -> PlacementReconciliationOutcome:
    if observation.ref_id != request.ref_id:
        raise ValueError(
            "reconciliation observation ref_id "
            "does not match request"
        )

    return PlacementReconciliationOutcome(
        request=request,
        status=observation.status,
        checked_at=observation.checked_at,
        broker_order_id=observation.broker_order_id,
        message=observation.message,
    )


class PlacementReconciliationReviewService:
    def __init__(
        self,
        journal: PlacementAttemptJournal,
        policy: ReconciliationReviewPolicy,
    ) -> None:
        self._journal = journal
        self._policy = policy

    def evaluate(
        self,
        request: PlacementReconciliationRequest,
    ) -> ReconciliationReviewDecision:
        records = (
            self._journal
            .list_reconciliation_observations(
                request.ref_id
            )
        )

        observations = [
            restore_reconciliation_outcome(
                request,
                record,
            )
            for record in records
        ]

        return self._policy.evaluate(
            request,
            observations,
        )