from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_decision import (
    EntryDecision,
)


class EntryProposalError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EquityEntryProposal:
    symbol: str
    budget: Decimal
    reference_price: Decimal
    estimated_quantity: Decimal
    proposed_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if self.symbol != self.symbol.upper():
            raise ValueError(
                "symbol must be uppercase"
            )

        for field_name, value in (
            ("budget", self.budget),
            (
                "reference_price",
                self.reference_price,
            ),
            (
                "estimated_quantity",
                self.estimated_quantity,
            ),
        ):
            if not value.is_finite():
                raise ValueError(
                    f"{field_name} must be finite"
                )

            if value <= 0:
                raise ValueError(
                    f"{field_name} must be "
                    "greater than zero"
                )

        if (
            self.proposed_at.tzinfo is None
            or self.proposed_at.utcoffset()
            is None
        ):
            raise ValueError(
                "proposed_at must be timezone-aware"
            )


def build_equity_entry_proposal(
    *,
    market: BullishEntrySnapshot,
    request: EntryRiskRequest,
    decision: EntryDecision,
) -> EquityEntryProposal:
    if not decision.approved:
        raise EntryProposalError(
            "entry decision must be approved "
            "before building proposal"
        )

    if request.asset_type is not AssetType.EQUITY:
        raise EntryProposalError(
            "equity entry proposal requires "
            "an equity request"
        )

    if market.symbol != request.symbol:
        raise EntryProposalError(
            "market snapshot symbol must match "
            "entry request symbol"
        )

    estimated_quantity = (
        request.opening_cost
        / market.price
    )

    return EquityEntryProposal(
        symbol=request.symbol,
        budget=request.opening_cost,
        reference_price=market.price,
        estimated_quantity=estimated_quantity,
        proposed_at=market.observed_at,
    )