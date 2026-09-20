from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.brokers.robinhood.candidate_market_data import (
    load_robinhood_equity_candidate_market_data,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
    EquityCandidateMarketData,
    build_equity_review_candidate,
)
from stock_agent.orchestration.entry_review_batch import (
    EquityEntryReviewCandidate,
)


@dataclass(frozen=True, slots=True)
class EquityCandidateLoadItem:
    symbol: str
    market_data: EquityCandidateMarketData | None = None
    candidate: EquityEntryReviewCandidate | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        succeeded = (
            self.market_data is not None
            and self.candidate is not None
            and self.error is None
        )

        failed = (
            self.market_data is None
            and self.candidate is None
            and self.error is not None
        )

        if not (
            succeeded
            or failed
        ):
            raise ValueError(
                "candidate load item must be "
                "either successful or failed"
            )

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class EquityCandidateLoadOutcome:
    items: tuple[
        EquityCandidateLoadItem,
        ...,
    ]

    @property
    def candidates(
        self,
    ) -> tuple[
        EquityEntryReviewCandidate,
        ...,
    ]:
        return tuple(
            item.candidate
            for item in self.items
            if item.candidate is not None
        )

    @property
    def errors(
        self,
    ) -> tuple[
        EquityCandidateLoadItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if item.error is not None
        )

    @property
    def candidate_count(
        self,
    ) -> int:
        return len(
            self.candidates
        )

    @property
    def error_count(
        self,
    ) -> int:
        return len(
            self.errors
        )


def load_robinhood_equity_review_candidates(
    invoker: MCPToolInvoker,
    *,
    symbols: tuple[
        str,
        ...,
    ],
    session_start: datetime,
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> EquityCandidateLoadOutcome:
    if (
        session_start.tzinfo is None
        or session_start.utcoffset() is None
    ):
        raise ValueError(
            "session_start must be timezone-aware"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be timezone-aware"
        )

    if session_start >= evaluated_at:
        raise ValueError(
            "session_start must be before evaluated_at"
        )

    if not budget.is_finite():
        raise ValueError(
            "budget must be finite"
        )

    if budget <= 0:
        raise ValueError(
            "budget must be greater than zero"
        )

    seen_symbols = set()

    for symbol in symbols:
        if not symbol.strip():
            raise ValueError(
                "symbols cannot contain empty values"
            )

        if symbol != symbol.upper():
            raise ValueError(
                "symbols must be uppercase"
            )

        if symbol in seen_symbols:
            raise ValueError(
                "symbols cannot contain duplicates"
            )

        seen_symbols.add(
            symbol
        )

    items = []

    for symbol in symbols:
        try:
            market_data = (
                load_robinhood_equity_candidate_market_data(
                    invoker,
                    symbol=symbol,
                    session_start=(
                        session_start
                    ),
                    evaluated_at=(
                        evaluated_at
                    ),
                )
            )

            candidate = (
                build_equity_review_candidate(
                    market_data,
                    budget=budget,
                )
            )

        except Exception as error:
            items.append(
                EquityCandidateLoadItem(
                    symbol=symbol,
                    error=error,
                )
            )

            continue

        items.append(
            EquityCandidateLoadItem(
                symbol=symbol,
                market_data=(
                    market_data
                ),
                candidate=candidate,
            )
        )

    return EquityCandidateLoadOutcome(
        items=tuple(
            items
        )
    )