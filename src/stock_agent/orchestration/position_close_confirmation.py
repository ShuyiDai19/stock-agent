from dataclasses import dataclass, replace
from datetime import datetime

from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


class PositionCloseConfirmationError(
    ValueError
):
    pass


@dataclass(frozen=True, slots=True)
class PositionCloseConfirmation:
    position_id: str
    execution: RobinhoodOrderExecutionSnapshot
    confirmed_at: datetime

    def __post_init__(
        self,
    ) -> None:
        if not self.position_id.strip():
            raise ValueError(
                "position_id cannot be empty"
            )

        if (
            self.confirmed_at.tzinfo is None
            or self.confirmed_at.utcoffset()
            is None
        ):
            raise ValueError(
                "confirmed_at must be "
                "timezone-aware"
            )


def apply_position_close_confirmation(
    state: PositionRuntimeState,
    confirmation: PositionCloseConfirmation,
) -> PositionRuntimeState:
    if (
        confirmation.position_id
        != state.position_id
    ):
        raise PositionCloseConfirmationError(
            "close confirmation position_id "
            "does not match position state"
        )

    if not (
        confirmation.execution
        .confirms_full_fill
    ):
        raise PositionCloseConfirmationError(
            "close confirmation requires "
            "a fully filled execution"
        )

    if (
        confirmation.confirmed_at
        < state.last_reconciled_at
    ):
        raise PositionCloseConfirmationError(
            "close confirmation cannot precede "
            "last reconciliation"
        )

    if (
        state.status
        is PositionStateStatus.CLOSED
    ):
        return state

    if (
        state.status
        is not PositionStateStatus.CLOSING
    ):
        raise PositionCloseConfirmationError(
            "only a closing position can "
            "transition to closed"
        )

    return replace(
        state,
        remaining_quantity=0,
        last_reconciled_at=(
            confirmation.confirmed_at
        ),
        status=PositionStateStatus.CLOSED,
        version=state.version + 1,
    )