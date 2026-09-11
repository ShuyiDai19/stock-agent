from dataclasses import dataclass

from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptJournal,
    PlacementAttemptRecord,
)
from stock_agent.brokers.robinhood.placement_recovery import (
    PlacementRecoveryAction,
    PlacementRecoveryPlan,
    PlacementRecoveryPlanner,
)
from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationOutcome,
    build_placement_reconciliation_request,
)
from stock_agent.brokers.robinhood.reconciler import (
    PlacementReconciler,
)


@dataclass(frozen=True)
class PlacementRecoveryResult:
    record: PlacementAttemptRecord
    plan: PlacementRecoveryPlan
    outcome: PlacementReconciliationOutcome | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        if self.plan.record != self.record:
            raise ValueError(
                "recovery plan record does not match result record"
            )

        if (
            self.plan.action
            is PlacementRecoveryAction.RECONCILE
        ):
            if (self.outcome is None) == (self.error is None):
                raise ValueError(
                    "reconcile recovery result requires "
                    "exactly one outcome or error"
                )
        elif (
            self.outcome is not None
            or self.error is not None
        ):
            raise ValueError(
                "non-reconcile recovery result cannot "
                "contain outcome or error"
            )


class PlacementRecoveryService:
    def __init__(
        self,
        journal: PlacementAttemptJournal,
        planner: PlacementRecoveryPlanner,
        reconciler: PlacementReconciler,
    ) -> None:
        self._journal = journal
        self._planner = planner
        self._reconciler = reconciler

    def recover(
        self,
    ) -> list[PlacementRecoveryResult]:
        results: list[PlacementRecoveryResult] = []

        for record in self._journal.list_unresolved():
            plan = self._planner.plan(
                record
            )

            if (
                plan.action
                is not PlacementRecoveryAction.RECONCILE
            ):
                results.append(
                    PlacementRecoveryResult(
                        record=record,
                        plan=plan,
                    )
                )
                continue

            request = (
                build_placement_reconciliation_request(
                    record.submission,
                    placement_attempted_at=(
                        record.placement_attempted_at
                    ),
                )
            )

            try:
                outcome = self._reconciler.reconcile(
                    request
                )
            except Exception as exc:
                results.append(
                    PlacementRecoveryResult(
                        record=record,
                        plan=plan,
                        error=exc,
                    )
                )
                continue

            results.append(
                PlacementRecoveryResult(
                    record=record,
                    plan=plan,
                    outcome=outcome,
                )
            )

        return results