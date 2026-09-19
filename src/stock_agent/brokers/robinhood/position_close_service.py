from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.domain import AssetType
from stock_agent.orchestration.position_close_confirmation import (
    PositionCloseConfirmation,
    PositionCloseConfirmationError,
    apply_position_close_confirmation,
)
from stock_agent.state import (
    PositionStateNotFoundError,
    PositionStateStore,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


class EquityOrderExecutionReader(Protocol):
    def read(
        self,
        *,
        account_number: str,
        broker_order_id: str,
        ref_id: str,
    ) -> RobinhoodOrderExecutionSnapshot | None:
        ...


class EquityPositionCloseConfirmationService:
    def __init__(
        self,
        store: PositionStateStore,
        reader: EquityOrderExecutionReader,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._reader = reader
        self._clock = clock

    def confirm_if_filled(
        self,
        *,
        position_id: str,
        broker_order_id: str,
        ref_id: str,
    ) -> PositionRuntimeState | None:
        if not position_id.strip():
            raise ValueError(
                "position_id cannot be empty"
            )

        if not broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if not ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        state = self._store.get(
            position_id
        )

        if state is None:
            raise PositionStateNotFoundError(
                f"position state not found: {position_id}"
            )

        if (
            state.asset_type
            is not AssetType.EQUITY
        ):
            raise PositionCloseConfirmationError(
                "equity close confirmation service "
                "requires an equity position"
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
                "be confirmed closed"
            )

        execution = self._reader.read(
            account_number=state.account_number,
            broker_order_id=broker_order_id,
            ref_id=ref_id,
        )

        if execution is None:
            return None

        confirmation = PositionCloseConfirmation(
            position_id=state.position_id,
            execution=execution,
            confirmed_at=self._clock(),
        )

        updated = (
            apply_position_close_confirmation(
                state,
                confirmation,
            )
        )

        self._store.update(
            updated,
            expected_version=state.version,
        )

        return updated