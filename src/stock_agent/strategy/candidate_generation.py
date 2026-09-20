from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.orchestration.entry_review_batch import (
    EquityEntryReviewCandidate,
)
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_execution import (
    EquityExecutionQuote,
)


DEFAULT_ENTRY_BUDGET = Decimal("8")


@dataclass(frozen=True, slots=True)
class EquityCandidateMarketData:
    symbol: str
    price: Decimal
    session_open: Decimal
    vwap: Decimal
    recent_5m_closes: tuple[
        Decimal,
        Decimal,
        Decimal,
    ]
    bid: Decimal
    ask: Decimal
    signal_observed_at: datetime
    quote_observed_at: datetime

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
            ("price", self.price),
            ("session_open", self.session_open),
            ("vwap", self.vwap),
            ("bid", self.bid),
            ("ask", self.ask),
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

        if self.ask < self.bid:
            raise ValueError(
                "ask cannot be below bid"
            )

        for close in self.recent_5m_closes:
            if (
                not close.is_finite()
                or close <= 0
            ):
                raise ValueError(
                    "recent 5m closes must "
                    "be positive and finite"
                )

        for field_name, value in (
            (
                "signal_observed_at",
                self.signal_observed_at,
            ),
            (
                "quote_observed_at",
                self.quote_observed_at,
            ),
        ):
            if (
                value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError(
                    f"{field_name} must be "
                    "timezone-aware"
                )


def compute_equity_candidate_priority(
    data: EquityCandidateMarketData,
) -> Decimal:
    """
    Ranking only.

    This does NOT approve a trade. Entry confirmation
    and risk gates still make the actual decision.
    """

    vwap_edge = (
        data.price - data.vwap
    ) / data.vwap

    open_edge = (
        data.price - data.session_open
    ) / data.session_open

    first_close = (
        data.recent_5m_closes[0]
    )

    latest_close = (
        data.recent_5m_closes[-1]
    )

    short_momentum = (
        latest_close - first_close
    ) / first_close

    return (
        vwap_edge
        + open_edge
        + short_momentum
    )


def build_equity_review_candidate(
    data: EquityCandidateMarketData,
    *,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> EquityEntryReviewCandidate:
    if not budget.is_finite():
        raise ValueError(
            "budget must be finite"
        )

    if budget <= 0:
        raise ValueError(
            "budget must be greater than zero"
        )

    market = BullishEntrySnapshot(
        symbol=data.symbol,
        price=data.price,
        session_open=data.session_open,
        vwap=data.vwap,
        recent_5m_closes=(
            data.recent_5m_closes
        ),
        observed_at=(
            data.signal_observed_at
        ),
    )

    request = EntryRiskRequest(
        symbol=data.symbol,
        asset_type=AssetType.EQUITY,
        opening_cost=budget,
    )

    execution_quote = (
        EquityExecutionQuote(
            symbol=data.symbol,
            bid=data.bid,
            ask=data.ask,
            observed_at=(
                data.quote_observed_at
            ),
        )
    )

    return EquityEntryReviewCandidate(
        market=market,
        request=request,
        execution_quote=execution_quote,
        priority_score=(
            compute_equity_candidate_priority(
                data
            )
        ),
    )


def build_equity_review_candidates(
    market_data: tuple[
        EquityCandidateMarketData,
        ...,
    ],
    *,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> tuple[
    EquityEntryReviewCandidate,
    ...,
]:
    return tuple(
        build_equity_review_candidate(
            data,
            budget=budget,
        )
        for data in market_data
    )