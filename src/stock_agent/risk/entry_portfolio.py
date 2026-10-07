from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from stock_agent.domain import AssetType


MIN_OPENING_COST = Decimal("5")
MAX_OPENING_COST = Decimal("5")
MAX_TOTAL_OPENING_COST = Decimal("20")
MAX_OPEN_POSITIONS = 2
MAX_OPTION_POSITIONS = 1


class EntryRiskReason(StrEnum):
    OPENING_COST_TOO_SMALL = (
        "opening_cost_too_small"
    )
    OPENING_COST_TOO_LARGE = (
        "opening_cost_too_large"
    )
    MAX_OPEN_POSITIONS_REACHED = (
        "max_open_positions_reached"
    )
    MAX_OPTION_POSITIONS_REACHED = (
        "max_option_positions_reached"
    )
    TOTAL_OPENING_COST_EXCEEDED = (
        "total_opening_cost_exceeded"
    )
    DUPLICATE_UNDERLYING = (
        "duplicate_underlying"
    )


@dataclass(frozen=True, slots=True)
class OpenPositionRiskSnapshot:
    symbol: str
    asset_type: AssetType
    opening_cost: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if self.symbol != self.symbol.upper():
            raise ValueError(
                "symbol must be uppercase"
            )

        if not self.opening_cost.is_finite():
            raise ValueError(
                "opening_cost must be finite"
            )

        if self.opening_cost <= 0:
            raise ValueError(
                "opening_cost must be greater than zero"
            )


@dataclass(frozen=True, slots=True)
class EntryRiskRequest:
    symbol: str
    asset_type: AssetType
    opening_cost: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if self.symbol != self.symbol.upper():
            raise ValueError(
                "symbol must be uppercase"
            )

        if not self.opening_cost.is_finite():
            raise ValueError(
                "opening_cost must be finite"
            )

        if self.opening_cost <= 0:
            raise ValueError(
                "opening_cost must be greater than zero"
            )


@dataclass(frozen=True, slots=True)
class EntryRiskDecision:
    reasons: frozenset[EntryRiskReason]

    @property
    def approved(self) -> bool:
        return not self.reasons


def evaluate_entry_portfolio_risk(
    request: EntryRiskRequest,
    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...
    ],
) -> EntryRiskDecision:
    reasons: set[
        EntryRiskReason
    ] = set()

    if request.opening_cost < MIN_OPENING_COST:
        reasons.add(
            EntryRiskReason
            .OPENING_COST_TOO_SMALL
        )

    if request.opening_cost > MAX_OPENING_COST:
        reasons.add(
            EntryRiskReason
            .OPENING_COST_TOO_LARGE
        )

    if (
        len(open_positions)
        >= MAX_OPEN_POSITIONS
    ):
        reasons.add(
            EntryRiskReason
            .MAX_OPEN_POSITIONS_REACHED
        )

    if any(
        position.symbol == request.symbol
        for position in open_positions
    ):
        reasons.add(
            EntryRiskReason
            .DUPLICATE_UNDERLYING
        )

    option_count = sum(
        1
        for position in open_positions
        if position.asset_type
        is AssetType.OPTION
    )

    if (
        request.asset_type is AssetType.OPTION
        and option_count
        >= MAX_OPTION_POSITIONS
    ):
        reasons.add(
            EntryRiskReason
            .MAX_OPTION_POSITIONS_REACHED
        )

    total_opening_cost = sum(
        (
            position.opening_cost
            for position in open_positions
        ),
        Decimal("0"),
    )

    if (
        total_opening_cost
        + request.opening_cost
        > MAX_TOTAL_OPENING_COST
    ):
        reasons.add(
            EntryRiskReason
            .TOTAL_OPENING_COST_EXCEEDED
        )

    return EntryRiskDecision(
        reasons=frozenset(
            reasons
        )
    )