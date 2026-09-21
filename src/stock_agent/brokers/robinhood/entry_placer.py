from collections.abc import Callable
from datetime import (
    datetime,
    timezone,
)

from stock_agent.brokers.robinhood.entry_placement import (
    RobinhoodEquityEntryPlacementResult,
    SQLiteEquityEntryPlacementJournal,
    place_robinhood_equity_entry,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.orchestration.entry_review_batch import (
    EntryReviewBatchItem,
)

def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


class RobinhoodApprovedEquityEntryPlacer:
    def __init__(
        self,
        invoker: MCPToolInvoker,
        journal: SQLiteEquityEntryPlacementJournal,
        *,
        clock: Callable[[], datetime] = _utc_now,
        ref_id_factory: (
            Callable[[], str]
            | None
        ) = None,
    ) -> None:
        self._invoker = invoker
        self._journal = journal
        self._clock = clock
        self._ref_id_factory = (
            ref_id_factory
        )

    def place(
        self,
        item: EntryReviewBatchItem,
        *,
        account_number: str,
        attempted_at: datetime,
    ) -> RobinhoodEquityEntryPlacementResult:
        if not item.eligible_to_place:
            raise ValueError(
                "entry review item is not "
                "eligible for placement"
            )

        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if (
            attempted_at.tzinfo is None
            or attempted_at.utcoffset()
            is None
        ):
            raise ValueError(
                "attempted_at must be "
                "timezone-aware"
            )

        outcome = item.outcome

        if outcome is None:
            raise ValueError(
                "eligible entry item must "
                "contain review outcome"
            )

        review = outcome.review

        if review is None:
            raise ValueError(
                "eligible entry item must "
                "contain broker review"
            )

        if (
            review.plan.symbol
            != item.symbol
        ):
            raise ValueError(
                "entry review symbol does "
                "not match batch item"
            )

        if self._ref_id_factory is None:
            return (
                place_robinhood_equity_entry(
                    self._invoker,
                    self._journal,
                    account_number=(
                        account_number
                    ),
                    review=review,
                    clock=self._clock,
                )
            )

        return (
            place_robinhood_equity_entry(
                self._invoker,
                self._journal,
                account_number=(
                    account_number
                ),
                review=review,
                clock=self._clock,
                ref_id_factory=(
                    self._ref_id_factory
                ),
            )
        )