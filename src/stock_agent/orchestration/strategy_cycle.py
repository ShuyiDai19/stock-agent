from dataclasses import dataclass
from datetime import datetime

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.orchestration.entry_review_batch import (
    EntryReviewBatchItem,
    EntryReviewBatchOutcome,
    EquityEntryReviewCandidate,
    run_equity_entry_review_batch,
)
from stock_agent.risk.entry_portfolio import (
    OpenPositionRiskSnapshot,
)


@dataclass(frozen=True, slots=True)
class EquityStrategyCycleInput:
    account_number: str

    candidates: tuple[
        EquityEntryReviewCandidate,
        ...,
    ]

    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...,
    ]

    evaluated_at: datetime

    def __post_init__(self) -> None:
        if not self.account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if (
            self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset()
            is None
        ):
            raise ValueError(
                "evaluated_at must be timezone-aware"
            )


@dataclass(frozen=True, slots=True)
class EquityStrategyCycleOutcome:
    cycle_input: EquityStrategyCycleInput
    review_batch: EntryReviewBatchOutcome

    @property
    def items(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return self.review_batch.items

    @property
    def eligible_entries(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return (
            self.review_batch
            .eligible_items
        )

    @property
    def errors(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if item.error is not None
        )

    @property
    def reviewed_candidate_count(
        self,
    ) -> int:
        return len(
            self.items
        )

    @property
    def eligible_entry_count(
        self,
    ) -> int:
        return len(
            self.eligible_entries
        )

    @property
    def error_count(
        self,
    ) -> int:
        return len(
            self.errors
        )


def run_equity_strategy_cycle(
    invoker: MCPToolInvoker,
    cycle_input: EquityStrategyCycleInput,
) -> EquityStrategyCycleOutcome:
    review_batch = (
        run_equity_entry_review_batch(
            invoker,
            account_number=(
                cycle_input.account_number
            ),
            candidates=(
                cycle_input.candidates
            ),
            open_positions=(
                cycle_input.open_positions
            ),
            evaluated_at=(
                cycle_input.evaluated_at
            ),
        )
    )

    return EquityStrategyCycleOutcome(
        cycle_input=cycle_input,
        review_batch=review_batch,
    )