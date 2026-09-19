from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.orchestration.entry_review_cycle import (
    EntryReviewCycleOutcome,
    run_equity_entry_review_cycle,
)
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_execution import (
    EquityExecutionQuote,
)


@dataclass(frozen=True, slots=True)
class EquityEntryReviewCandidate:
    market: BullishEntrySnapshot
    request: EntryRiskRequest
    execution_quote: EquityExecutionQuote
    priority_score: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        symbols = {
            self.market.symbol,
            self.request.symbol,
            self.execution_quote.symbol,
        }

        if len(symbols) != 1:
            raise ValueError(
                "candidate market, request, and "
                "execution quote symbols must match"
            )

        if not self.priority_score.is_finite():
            raise ValueError(
                "priority_score must be finite"
            )

    @property
    def symbol(self) -> str:
        return self.request.symbol


@dataclass(frozen=True, slots=True)
class EntryReviewBatchItem:
    symbol: str
    outcome: EntryReviewCycleOutcome | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        if (
            self.outcome is None
            and self.error is None
        ):
            raise ValueError(
                "batch item requires outcome or error"
            )

        if (
            self.outcome is not None
            and self.error is not None
        ):
            raise ValueError(
                "batch item cannot contain "
                "both outcome and error"
            )

    @property
    def eligible_to_place(self) -> bool:
        return (
            self.outcome is not None
            and self.outcome.eligible_to_place
        )


@dataclass(frozen=True, slots=True)
class EntryReviewBatchOutcome:
    items: tuple[
        EntryReviewBatchItem,
        ...,
    ]

    @property
    def eligible_items(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if item.eligible_to_place
        )


def run_equity_entry_review_batch(
    invoker: MCPToolInvoker,
    *,
    account_number: str,
    candidates: tuple[
        EquityEntryReviewCandidate,
        ...,
    ],
    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...,
    ],
    evaluated_at: datetime,
) -> EntryReviewBatchOutcome:
    if not account_number.strip():
        raise ValueError(
            "account_number cannot be empty"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be timezone-aware"
        )

    provisional_positions = list(
        open_positions
    )

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.priority_score,
            candidate.symbol,
        ),
    )

    items = []

    for candidate in ranked_candidates:
        try:
            outcome = (
                run_equity_entry_review_cycle(
                    invoker,
                    account_number=(
                        account_number
                    ),
                    market=candidate.market,
                    request=candidate.request,
                    open_positions=tuple(
                        provisional_positions
                    ),
                    execution_quote=(
                        candidate.execution_quote
                    ),
                    evaluated_at=(
                        evaluated_at
                    ),
                )
            )
        except Exception as error:
            items.append(
                EntryReviewBatchItem(
                    symbol=candidate.symbol,
                    error=error,
                )
            )

            continue

        item = EntryReviewBatchItem(
            symbol=candidate.symbol,
            outcome=outcome,
        )

        items.append(
            item
        )

        if not item.eligible_to_place:
            continue

        provisional_positions.append(
            OpenPositionRiskSnapshot(
                symbol=(
                    candidate.request.symbol
                ),
                asset_type=(
                    candidate.request.asset_type
                ),
                opening_cost=(
                    candidate.request.opening_cost
                ),
            )
        )

    return EntryReviewBatchOutcome(
        items=tuple(
            items
        )
    )