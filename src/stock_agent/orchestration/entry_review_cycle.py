from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from stock_agent.brokers.robinhood.entry_review import (
    RobinhoodEquityEntryReview,
    review_robinhood_equity_entry,
    revalidate_robinhood_equity_entry_review,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_decision import (
    EntryDecision,
    evaluate_entry_decision,
)
from stock_agent.strategy.entry_execution import (
    EntryExecutionNotAllowedError,
    EquityEntryExecutionPlan,
    EquityExecutionQuote,
    build_equity_entry_execution_plan,
)
from stock_agent.strategy.entry_proposal import (
    EquityEntryProposal,
    build_equity_entry_proposal,
)


class EntryReviewCycleStatus(StrEnum):
    NO_TRADE = "no_trade"
    REVIEW_REJECTED = "review_rejected"
    REVIEW_APPROVED = "review_approved"


@dataclass(frozen=True, slots=True)
class EntryReviewCycleOutcome:
    symbol: str
    status: EntryReviewCycleStatus
    decision: EntryDecision
    proposal: EquityEntryProposal | None = None
    execution_plan: EquityEntryExecutionPlan | None = None
    review: RobinhoodEquityEntryReview | None = None
    reason: str | None = None

    @property
    def eligible_to_place(self) -> bool:
        return (
            self.status
            is EntryReviewCycleStatus.REVIEW_APPROVED
        )


def run_equity_entry_review_cycle(
    invoker: MCPToolInvoker,
    *,
    account_number: str,
    market: BullishEntrySnapshot,
    request: EntryRiskRequest,
    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...,
    ],
    execution_quote: EquityExecutionQuote,
    evaluated_at: datetime,
    execution_clock: (
        Callable[[], datetime]
        | None
    ) = None,
) -> EntryReviewCycleOutcome:
    decision = evaluate_entry_decision(
        market=market,
        request=request,
        open_positions=open_positions,
    )

    if not decision.approved:
        return EntryReviewCycleOutcome(
            symbol=request.symbol,
            status=(
                EntryReviewCycleStatus.NO_TRADE
            ),
            decision=decision,
            reason=(
                "entry confirmation or "
                "portfolio risk rejected"
            ),
        )

    proposal = build_equity_entry_proposal(
        market=market,
        request=request,
        decision=decision,
    )

    execution_evaluated_at = (
        evaluated_at
        if execution_clock is None
        else execution_clock()
    )

    if (
        execution_evaluated_at.tzinfo is None
        or execution_evaluated_at.utcoffset()
        is None
    ):
        raise ValueError(
            "execution clock must return "
            "timezone-aware datetime"
        )

    try:
        execution_plan = (
            build_equity_entry_execution_plan(
                proposal,
                execution_quote,
                evaluated_at=(
                    execution_evaluated_at
                ),
            )
        )
    except EntryExecutionNotAllowedError as error:
        return EntryReviewCycleOutcome(
            symbol=request.symbol,
            status=(
                EntryReviewCycleStatus.NO_TRADE
            ),
            decision=decision,
            proposal=proposal,
            reason=str(error),
        )

    review = review_robinhood_equity_entry(
        invoker,
        account_number=account_number,
        plan=execution_plan,
    )

    review_evaluated_at = (
        evaluated_at
        if execution_clock is None
        else execution_clock()
    )

    if (
        review_evaluated_at.tzinfo is None
        or review_evaluated_at.utcoffset()
        is None
    ):
        raise ValueError(
            "execution clock must return "
            "timezone-aware datetime"
        )

    if not review.approved:
        return EntryReviewCycleOutcome(
            symbol=request.symbol,
            status=(
                EntryReviewCycleStatus
                .REVIEW_REJECTED
            ),
            decision=decision,
            proposal=proposal,
            execution_plan=execution_plan,
            review=review,
            reason=(
                "Robinhood order review "
                "returned order checks"
            ),
        )

    try:
        revalidate_robinhood_equity_entry_review(
            review,
            evaluated_at=(
                review_evaluated_at
            ),
        )
    except EntryExecutionNotAllowedError as error:
        return EntryReviewCycleOutcome(
            symbol=request.symbol,
            status=(
                EntryReviewCycleStatus.NO_TRADE
            ),
            decision=decision,
            proposal=proposal,
            execution_plan=execution_plan,
            review=review,
            reason=str(error),
        )

    return EntryReviewCycleOutcome(
        symbol=request.symbol,
        status=(
            EntryReviewCycleStatus
            .REVIEW_APPROVED
        ),
        decision=decision,
        proposal=proposal,
        execution_plan=execution_plan,
        review=review,
    )