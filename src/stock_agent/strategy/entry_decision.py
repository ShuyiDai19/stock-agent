from dataclasses import dataclass

from stock_agent.risk.entry_portfolio import (
    EntryRiskDecision,
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
    evaluate_entry_portfolio_risk,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
    EntryConfirmationDecision,
    evaluate_bullish_entry_confirmation,
)


@dataclass(frozen=True, slots=True)
class EntryDecision:
    confirmation: EntryConfirmationDecision
    risk: EntryRiskDecision

    @property
    def approved(self) -> bool:
        return (
            self.confirmation.approved
            and self.risk.approved
        )


def evaluate_entry_decision(
    *,
    market: BullishEntrySnapshot,
    request: EntryRiskRequest,
    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...
    ],
) -> EntryDecision:
    if market.symbol != request.symbol:
        raise ValueError(
            "market snapshot symbol must match "
            "entry request symbol"
        )

    confirmation = (
        evaluate_bullish_entry_confirmation(
            market
        )
    )

    risk = evaluate_entry_portfolio_risk(
        request,
        open_positions,
    )

    return EntryDecision(
        confirmation=confirmation,
        risk=risk,
    )