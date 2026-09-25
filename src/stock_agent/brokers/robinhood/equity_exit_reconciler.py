from typing import Protocol

from stock_agent.brokers.robinhood.exit_state_reconciliation import (
    EquityExitStateReconciler,
)
from stock_agent.domain import AssetType
from stock_agent.state import (
    PositionStateStore,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


class EquityPositionCloseService(
    Protocol
):
    def confirm_if_filled(
        self,
        *,
        position_id: str,
    ) -> PositionRuntimeState | None:
        ...


class RobinhoodEquityExitReconciliationError(
    RuntimeError
):
    pass


class RobinhoodEquityExitReconciler:
    def __init__(
        self,
        state_reconciler: (
            EquityExitStateReconciler
        ),
        close_service: (
            EquityPositionCloseService
        ),
        store: PositionStateStore,
    ) -> None:
        self._state_reconciler = (
            state_reconciler
        )
        self._close_service = (
            close_service
        )
        self._store = store

    def reconcile(
        self,
        *,
        account_number: str,
    ) -> tuple[
        PositionRuntimeState,
        ...,
    ]:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        # First repair the dangerous crash window:
        #
        # broker exit exists
        # +
        # local position still ACTIVE
        #
        # -> CLOSING
        self._state_reconciler.reconcile(
            account_number=(
                account_number
            )
        )

        closing_states = (
            self._equity_closing_states(
                account_number=(
                    account_number
                )
            )
        )

        closed_positions: list[
            PositionRuntimeState
        ] = []

        for state in closing_states:
            confirmed = (
                self._close_service
                .confirm_if_filled(
                    position_id=(
                        state.position_id
                    )
                )
            )

            if confirmed is None:
                continue

            if (
                confirmed.status
                is not
                PositionStateStatus.CLOSED
            ):
                raise (
                    RobinhoodEquityExitReconciliationError(
                        "equity close confirmation "
                        "returned non-closed state"
                    )
                )

            closed_positions.append(
                confirmed
            )

        remaining_closing = (
            self._equity_closing_states(
                account_number=(
                    account_number
                )
            )
        )

        if remaining_closing:
            raise (
                RobinhoodEquityExitReconciliationError(
                    "equity exit reconciliation "
                    "left closing positions "
                    "unresolved"
                )
            )

        return tuple(
            closed_positions
        )

    def _equity_closing_states(
        self,
        *,
        account_number: str,
    ) -> tuple[
        PositionRuntimeState,
        ...,
    ]:
        states = (
            self._store.list_by_status(
                account_number=(
                    account_number
                ),
                statuses=(
                    PositionStateStatus
                    .CLOSING,
                ),
            )
        )

        return tuple(
            state
            for state in states
            if (
                state.asset_type
                is AssetType.EQUITY
            )
        )