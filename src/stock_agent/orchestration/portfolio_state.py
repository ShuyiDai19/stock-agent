from typing import Protocol

from stock_agent.domain import (
    AssetType,
)
from stock_agent.risk.entry_portfolio import (
    OpenPositionRiskSnapshot,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)


class PositionRiskStateStore(
    Protocol
):
    def list_by_status(
        self,
        *,
        account_number: str,
        statuses,
    ) -> list[
        PositionRuntimeState
    ]:
        ...


class UnsupportedOpenPositionRiskError(
    RuntimeError
):
    pass


def load_open_position_risk_snapshots(
    store: PositionRiskStateStore,
    *,
    account_number: str,
) -> tuple[
    OpenPositionRiskSnapshot,
    ...,
]:
    if not account_number.strip():
        raise ValueError(
            "account_number cannot be empty"
        )

    states = store.list_by_status(
        account_number=account_number,
        statuses=(
            PositionStateStatus.ACTIVE,
            PositionStateStatus.CLOSING,
            PositionStateStatus
            .RECONCILIATION_REQUIRED,
        ),
    )

    snapshots = []

    for state in sorted(
        states,
        key=lambda item: (
            item.position_id
        ),
    ):
        if (
            state.asset_type
            is not AssetType.EQUITY
        ):
            raise (
                UnsupportedOpenPositionRiskError(
                    "equity strategy cycle cannot "
                    "safely derive opening cost "
                    "for non-equity position "
                    f"{state.position_id}"
                )
            )

        opening_cost = (
            state.entry_price
            * state.remaining_quantity
        )

        if (
            not opening_cost.is_finite()
            or opening_cost <= 0
        ):
            raise ValueError(
                "derived opening cost must "
                "be positive and finite"
            )

        snapshots.append(
            OpenPositionRiskSnapshot(
                symbol=state.symbol,
                asset_type=(
                    state.asset_type
                ),
                opening_cost=(
                    opening_cost
                ),
            )
        )

    return tuple(
        snapshots
    )