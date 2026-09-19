from typing import Protocol

from stock_agent.brokers.robinhood.closing_order_provenance import (
    resolve_closing_order_provenance,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptJournal,
)
from stock_agent.domain import AssetType
from stock_agent.orchestration.position_close_confirmation import (
    PositionCloseConfirmationError,
)
from stock_agent.state.models import (
    PositionRuntimeState,
)


class EquityPositionCloseConfirmer(Protocol):
    def confirm_if_filled(
        self,
        *,
        position_id: str,
        broker_order_id: str,
        ref_id: str,
    ) -> PositionRuntimeState | None:
        ...


class JournalBackedEquityPositionCloseService:
    def __init__(
        self,
        journal: PlacementAttemptJournal,
        close_service: EquityPositionCloseConfirmer,
    ) -> None:
        self._journal = journal
        self._close_service = close_service

    def confirm_if_filled(
        self,
        *,
        position_id: str,
    ) -> PositionRuntimeState | None:
        if not position_id.strip():
            raise ValueError(
                "position_id cannot be empty"
            )

        provenance = (
            resolve_closing_order_provenance(
                self._journal.list_resolved(),
                position_id=position_id,
            )
        )

        if provenance is None:
            return None

        if provenance.asset_type is not AssetType.EQUITY:
            raise PositionCloseConfirmationError(
                "equity close confirmation requires "
                "equity closing-order provenance"
            )

        return self._close_service.confirm_if_filled(
            position_id=provenance.position_id,
            broker_order_id=(
                provenance.broker_order_id
            ),
            ref_id=provenance.ref_id,
        )