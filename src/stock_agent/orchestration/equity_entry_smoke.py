from dataclasses import replace
from decimal import Decimal

from stock_agent.brokers.robinhood.candidate_market_data import (
    load_robinhood_equity_candidate_market_data,
)
from stock_agent.orchestration.candidate_loading import (
    EquityCandidateLoadItem,
    EquityCandidateLoadOutcome,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
    build_equity_review_candidate,
)


_SMOKE_SIGNAL_DISCOUNT = Decimal(
    "0.99"
)


def build_deterministic_equity_smoke_loader(
    *,
    smoke_symbol: str,
):
    if not smoke_symbol.strip():
        raise ValueError(
            "smoke_symbol cannot be empty"
        )

    if smoke_symbol != smoke_symbol.upper():
        raise ValueError(
            "smoke_symbol must be uppercase"
        )

    def load(
        invoker,
        *,
        symbols: tuple[
            str,
            ...,
        ],
        session_start,
        evaluated_at,
        budget: Decimal = (
            DEFAULT_ENTRY_BUDGET
        ),
    ) -> EquityCandidateLoadOutcome:
        if symbols != (
            smoke_symbol,
        ):
            raise ValueError(
                "deterministic smoke loader "
                "requires exactly the configured "
                "smoke symbol"
            )

        real_data = (
            load_robinhood_equity_candidate_market_data(
                invoker,
                symbol=smoke_symbol,
                session_start=(
                    session_start
                ),
                evaluated_at=(
                    evaluated_at
                ),
            )
        )

        forced_reference = (
            real_data.price
            * _SMOKE_SIGNAL_DISCOUNT
        )

        smoke_data = replace(
            real_data,
            session_open=(
                forced_reference
            ),
            vwap=(
                forced_reference
            ),
            recent_5m_closes=(
                real_data.price,
                real_data.price,
                real_data.price,
            ),
        )

        candidate = (
            build_equity_review_candidate(
                smoke_data,
                budget=budget,
            )
        )

        return EquityCandidateLoadOutcome(
            items=(
                EquityCandidateLoadItem(
                    symbol=smoke_symbol,
                    market_data=(
                        smoke_data
                    ),
                    candidate=(
                        candidate
                    ),
                ),
            )
        )

    return load