from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from stock_agent.brokers.robinhood.position_reconciliation_policy import (
    EquityPositionReconciliationAction,
    EquityPositionReconciliationDecision,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.store import (
    PositionStateStore,
)


class EquityPositionReconciliationApplyStatus(
    StrEnum
):
    UPDATED = "updated"
    NO_STORE_CHANGE = "no_store_change"


@dataclass(frozen=True, slots=True)
class EquityPositionReconciliationApplyResult:
    decision: EquityPositionReconciliationDecision
    status: EquityPositionReconciliationApplyStatus
    updated_state: PositionRuntimeState | None


def _require_timezone_aware(
    value: datetime,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "reconciled_at must be timezone-aware"
        )


def apply_equity_position_reconciliation(
    *,
    store: PositionStateStore,
    decision: EquityPositionReconciliationDecision,
    reconciled_at: datetime,
) -> EquityPositionReconciliationApplyResult:
    _require_timezone_aware(
        reconciled_at
    )

    action = decision.action
    local_state = decision.outcome.local_state

    if (
        action
        is EquityPositionReconciliationAction
        .BROKER_ONLY_REVIEW
    ):
        if local_state is not None:
            raise ValueError(
                "BROKER_ONLY_REVIEW must not "
                "have a local position"
            )

        return EquityPositionReconciliationApplyResult(
            decision=decision,
            status=(
                EquityPositionReconciliationApplyStatus
                .NO_STORE_CHANGE
            ),
            updated_state=None,
        )

    if local_state is None:
        raise ValueError(
            "store mutation requires "
            "a local position"
        )

    if (
        action
        is EquityPositionReconciliationAction
        .MARK_RECONCILED
    ):
        updated_state = replace(
            local_state,
            last_reconciled_at=reconciled_at,
            version=local_state.version + 1,
        )

    elif (
        action
        is EquityPositionReconciliationAction
        .SYNC_CLOSING_QUANTITY
    ):
        broker_position = (
            decision.outcome.broker_position
        )

        if (
            local_state.status
            is not PositionStateStatus.CLOSING
        ):
            raise ValueError(
                "SYNC_CLOSING_QUANTITY requires "
                "a closing local position"
            )

        if broker_position is None:
            raise ValueError(
                "SYNC_CLOSING_QUANTITY requires "
                "a broker position"
            )

        if not (
            0
            < broker_position.quantity
            < local_state.remaining_quantity
        ):
            raise ValueError(
                "SYNC_CLOSING_QUANTITY requires "
                "a smaller positive broker quantity"
            )

        updated_state = replace(
            local_state,
            remaining_quantity=(
                broker_position.quantity
            ),
            last_reconciled_at=reconciled_at,
            version=local_state.version + 1,
        )

    elif (
        action
        is EquityPositionReconciliationAction
        .REQUIRE_RECONCILIATION
    ):
        updated_state = replace(
            local_state,
            last_reconciled_at=reconciled_at,
            status=(
                PositionStateStatus
                .RECONCILIATION_REQUIRED
            ),
            version=local_state.version + 1,
        )

    else:
        raise ValueError(
            f"unsupported reconciliation "
            f"action: {action}"
        )

    store.update(
        updated_state,
        expected_version=local_state.version,
    )

    return EquityPositionReconciliationApplyResult(
        decision=decision,
        status=(
            EquityPositionReconciliationApplyStatus
            .UPDATED
        ),
        updated_state=updated_state,
    )