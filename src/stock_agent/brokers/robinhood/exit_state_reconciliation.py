from dataclasses import dataclass

from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptJournal,
    PlacementAttemptRecord,
    PlacementAttemptStatus,
)
from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from stock_agent.orchestration.execution_state import (
    apply_execution_result_to_position_state,
)
from stock_agent.state import PositionStateStore
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
)


class EquityExitStateReconciliationError(
    RuntimeError
):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class EquityExitStateReconciliationResult:
    position_id: str
    repaired_state: (
        PositionRuntimeState | None
    )

    @property
    def repaired(self) -> bool:
        return (
            self.repaired_state
            is not None
        )


class EquityExitStateReconciler:
    def __init__(
        self,
        journal: PlacementAttemptJournal,
        store: PositionStateStore,
    ) -> None:
        self._journal = journal
        self._store = store

    def reconcile(
        self,
        *,
        account_number: str,
    ) -> tuple[
        EquityExitStateReconciliationResult,
        ...,
    ]:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        active_states = (
            self._store.list_by_status(
                account_number=(
                    account_number
                ),
                statuses=(
                    PositionStateStatus.ACTIVE,
                ),
            )
        )

        resolved_records = tuple(
            self._journal.list_resolved()
        )

        results = []

        for state in active_states:
            if (
                state.asset_type
                is not AssetType.EQUITY
            ):
                continue

            matching = [
                record
                for record in resolved_records
                if (
                    record.submission
                    .request.position_id
                    == state.position_id
                )
            ]

            if not matching:
                results.append(
                    EquityExitStateReconciliationResult(
                        position_id=(
                            state.position_id
                        ),
                        repaired_state=None,
                    )
                )
                continue

            if len(matching) != 1:
                raise (
                    EquityExitStateReconciliationError(
                        "active equity position has "
                        "multiple resolved closing "
                        "order placements"
                    )
                )

            record = matching[0]

            result = (
                self._build_execution_result(
                    state,
                    record,
                )
            )

            updated = (
                apply_execution_result_to_position_state(
                    self._store,
                    result,
                )
            )

            if (
                updated.status
                is not PositionStateStatus.CLOSING
            ):
                raise (
                    EquityExitStateReconciliationError(
                        "reconciled equity exit did "
                        "not produce CLOSING state"
                    )
                )

            results.append(
                EquityExitStateReconciliationResult(
                    position_id=(
                        state.position_id
                    ),
                    repaired_state=updated,
                )
            )

        return tuple(
            results
        )

    @staticmethod
    def _build_execution_result(
        state: PositionRuntimeState,
        record: PlacementAttemptRecord,
    ) -> ExecutionResult:
        request = (
            record.submission.request
        )

        if (
            request.asset_type
            is not AssetType.EQUITY
        ):
            raise (
                EquityExitStateReconciliationError(
                    "equity position matched "
                    "non-equity closing placement"
                )
            )

        if (
            request.account_number
            != state.account_number
        ):
            raise (
                EquityExitStateReconciliationError(
                    "closing placement account "
                    "does not match position"
                )
            )

        if request.symbol != state.symbol:
            raise EquityExitStateReconciliationError(
                "closing placement symbol "
                "does not match position"
            )

        if (
            request.action
            is not RobinhoodExitAction.EQUITY_SELL
        ):
            raise EquityExitStateReconciliationError(
                "resolved equity closing "
                "placement is not an equity sell"
            )

        if (
            request.quantity
            != state.remaining_quantity
        ):
            raise EquityExitStateReconciliationError(
                "closing placement quantity "
                "does not match remaining position"
            )

        if (
            record.status
            is PlacementAttemptStatus
            .ACKNOWLEDGED
        ):
            acknowledgement = (
                record.acknowledgement
            )

            if acknowledgement is None:
                raise (
                    EquityExitStateReconciliationError(
                        "acknowledged closing "
                        "placement is missing "
                        "acknowledgement"
                    )
                )

            broker_order_id = (
                acknowledgement
                .broker_order_id
            )

            submitted_at = (
                acknowledgement
                .acknowledged_at
            )

        elif (
            record.status
            is PlacementAttemptStatus
            .RECOVERED
        ):
            recovery = (
                record.recovery_evidence
            )

            if recovery is None:
                raise (
                    EquityExitStateReconciliationError(
                        "recovered closing "
                        "placement is missing "
                        "recovery evidence"
                    )
                )

            broker_order_id = (
                recovery.broker_order_id
            )

            submitted_at = (
                recovery.recovered_at
            )

        else:
            raise (
                EquityExitStateReconciliationError(
                    "resolved closing placement "
                    "has unsupported status"
                )
            )

        return ExecutionResult(
            position_id=(
                state.position_id
            ),
            status=(
                ExecutionStatus.SUBMITTED
            ),
            submitted_at=submitted_at,
            broker_order_id=(
                broker_order_id
            ),
            message=(
                "reconciled resolved Robinhood "
                "closing placement into local "
                "position state"
            ),
        )