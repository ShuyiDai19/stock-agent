from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
    RobinhoodEquityPositionType,
)
from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


class EquityPositionReconciliationError(
    ValueError
):
    pass


class EquityPositionReconciliationIssue(
    StrEnum
):
    BROKER_POSITION_MISSING = (
        "broker_position_missing"
    )
    LOCAL_POSITION_MISSING = (
        "local_position_missing"
    )
    QUANTITY_MISMATCH = (
        "quantity_mismatch"
    )
    SELLABILITY_RESTRICTED = (
        "sellability_restricted"
    )
    UNSUPPORTED_POSITION_TYPE = (
        "unsupported_position_type"
    )


@dataclass(frozen=True, slots=True)
class EquityPositionReconciliationOutcome:
    symbol: str
    local_state: PositionRuntimeState | None
    broker_position: (
        RobinhoodEquityPositionSnapshot | None
    )
    issues: frozenset[
        EquityPositionReconciliationIssue
    ]

    @property
    def matched(
        self,
    ) -> bool:
        return not self.issues


def _normalize_symbol(
    symbol: str,
) -> str:
    normalized = symbol.strip().upper()

    if not normalized:
        raise EquityPositionReconciliationError(
            "symbol cannot be empty"
        )

    return normalized


def reconcile_equity_positions(
    *,
    account_number: str,
    local_states: Iterable[
        PositionRuntimeState
    ],
    broker_positions: Iterable[
        RobinhoodEquityPositionSnapshot
    ],
) -> tuple[
    EquityPositionReconciliationOutcome,
    ...,
]:
    if not account_number.strip():
        raise EquityPositionReconciliationError(
            "account_number cannot be empty"
        )

    local_by_symbol: dict[
        str,
        PositionRuntimeState,
    ] = {}

    for state in local_states:
        if (
            state.account_number
            != account_number
        ):
            raise EquityPositionReconciliationError(
                "local position belongs to "
                "a different account"
            )

        if state.asset_type is not AssetType.EQUITY:
            raise EquityPositionReconciliationError(
                "equity reconciliation received "
                "a non-equity local position"
            )

        # CLOSED positions no longer represent
        # expected broker holdings.
        if (
            state.status
            is PositionStateStatus.CLOSED
        ):
            continue

        symbol = _normalize_symbol(
            state.symbol
        )

        if symbol in local_by_symbol:
            raise EquityPositionReconciliationError(
                "multiple open local positions "
                f"for symbol {symbol}"
            )

        local_by_symbol[symbol] = state

    broker_by_symbol: dict[
        str,
        RobinhoodEquityPositionSnapshot,
    ] = {}

    for position in broker_positions:
        symbol = _normalize_symbol(
            position.symbol
        )

        if symbol in broker_by_symbol:
            raise EquityPositionReconciliationError(
                "multiple broker positions "
                f"for symbol {symbol}"
            )

        broker_by_symbol[
            symbol
        ] = position

    symbols = sorted(
        set(local_by_symbol)
        | set(broker_by_symbol)
    )

    outcomes: list[
        EquityPositionReconciliationOutcome
    ] = []

    for symbol in symbols:
        local_state = local_by_symbol.get(
            symbol
        )
        broker_position = broker_by_symbol.get(
            symbol
        )

        issues: set[
            EquityPositionReconciliationIssue
        ] = set()

        if local_state is None:
            issues.add(
                EquityPositionReconciliationIssue
                .LOCAL_POSITION_MISSING
            )

        if broker_position is None:
            issues.add(
                EquityPositionReconciliationIssue
                .BROKER_POSITION_MISSING
            )

        if broker_position is not None:
            if (
                broker_position.position_type
                is not
                RobinhoodEquityPositionType.LONG
            ):
                issues.add(
                    EquityPositionReconciliationIssue
                    .UNSUPPORTED_POSITION_TYPE
                )

        if (
            local_state is not None
            and broker_position is not None
        ):
            if (
                broker_position.quantity
                != local_state.remaining_quantity
            ):
                issues.add(
                    EquityPositionReconciliationIssue
                    .QUANTITY_MISMATCH
                )

            if (
                broker_position
                .shares_available_for_sells
                < local_state.remaining_quantity
            ):
                issues.add(
                    EquityPositionReconciliationIssue
                    .SELLABILITY_RESTRICTED
                )

        outcomes.append(
            EquityPositionReconciliationOutcome(
                symbol=symbol,
                local_state=local_state,
                broker_position=(
                    broker_position
                ),
                issues=frozenset(
                    issues
                ),
            )
        )

    return tuple(outcomes)