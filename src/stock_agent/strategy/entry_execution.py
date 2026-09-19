from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR
from enum import StrEnum

from stock_agent.strategy.entry_proposal import (
    EquityEntryProposal,
)


DEFAULT_MAX_QUOTE_AGE = timedelta(
    seconds=30
)

DEFAULT_MAX_SPREAD_RATIO = Decimal(
    "0.002"
)


class EquityEntryExecutionMode(StrEnum):
    WHOLE_SHARE_LIMIT = (
        "whole_share_limit"
    )
    FRACTIONAL_MARKET = (
        "fractional_market"
    )


class EntryExecutionNotAllowedError(
    ValueError
):
    pass


@dataclass(frozen=True, slots=True)
class EquityExecutionQuote:
    symbol: str
    bid: Decimal
    ask: Decimal
    observed_at: datetime

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

        if (
            self.observed_at.tzinfo is None
            or self.observed_at.utcoffset()
            is None
        ):
            raise ValueError(
                "observed_at must be timezone-aware"
            )

    @property
    def midpoint(self) -> Decimal:
        return (
            self.bid + self.ask
        ) / Decimal("2")

    @property
    def spread_ratio(self) -> Decimal:
        return (
            self.ask - self.bid
        ) / self.midpoint


@dataclass(frozen=True, slots=True)
class EquityEntryExecutionPlan:
    symbol: str
    mode: EquityEntryExecutionMode
    budget: Decimal

    quantity: Decimal | None = None
    dollar_amount: Decimal | None = None
    limit_price: Decimal | None = None

    quote_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if not self.budget.is_finite():
            raise ValueError(
                "budget must be finite"
            )

        if self.budget <= 0:
            raise ValueError(
                "budget must be greater than zero"
            )

        if (
            self.mode
            is EquityEntryExecutionMode
            .WHOLE_SHARE_LIMIT
        ):
            if (
                self.quantity is None
                or self.limit_price is None
            ):
                raise ValueError(
                    "whole-share limit plan "
                    "requires quantity and limit_price"
                )

            if self.dollar_amount is not None:
                raise ValueError(
                    "whole-share limit plan cannot "
                    "contain dollar_amount"
                )

            if self.quantity < 1:
                raise ValueError(
                    "quantity must be at least one"
                )

            if self.quantity != (
                self.quantity.to_integral_value()
            ):
                raise ValueError(
                    "limit quantity must be "
                    "a whole number"
                )

            if (
                self.quantity
                * self.limit_price
                > self.budget
            ):
                raise ValueError(
                    "limit order cannot exceed budget"
                )

        elif (
            self.mode
            is EquityEntryExecutionMode
            .FRACTIONAL_MARKET
        ):
            if self.dollar_amount is None:
                raise ValueError(
                    "fractional market plan "
                    "requires dollar_amount"
                )

            if (
                self.quantity is not None
                or self.limit_price is not None
            ):
                raise ValueError(
                    "fractional market plan cannot "
                    "contain quantity or limit_price"
                )

            if self.dollar_amount != self.budget:
                raise ValueError(
                    "fractional market dollar_amount "
                    "must equal budget"
                )


def build_equity_entry_execution_plan(
    proposal: EquityEntryProposal,
    quote: EquityExecutionQuote,
    *,
    evaluated_at: datetime,
    max_quote_age: timedelta = (
        DEFAULT_MAX_QUOTE_AGE
    ),
    max_spread_ratio: Decimal = (
        DEFAULT_MAX_SPREAD_RATIO
    ),
) -> EquityEntryExecutionPlan:
    if proposal.symbol != quote.symbol:
        raise EntryExecutionNotAllowedError(
            "proposal symbol must match quote symbol"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be timezone-aware"
        )

    if max_quote_age <= timedelta(0):
        raise ValueError(
            "max_quote_age must be positive"
        )

    if (
        not max_spread_ratio.is_finite()
        or max_spread_ratio <= 0
    ):
        raise ValueError(
            "max_spread_ratio must be "
            "positive and finite"
        )

    quote_age = (
        evaluated_at
        - quote.observed_at
    )

    if quote_age < timedelta(0):
        raise EntryExecutionNotAllowedError(
            "quote cannot be from the future"
        )

    if quote_age > max_quote_age:
        raise EntryExecutionNotAllowedError(
            "quote is stale"
        )

    if (
        quote.spread_ratio
        > max_spread_ratio
    ):
        raise EntryExecutionNotAllowedError(
            "bid-ask spread exceeds entry limit"
        )

    whole_share_quantity = (
        proposal.budget
        / quote.ask
    ).to_integral_value(
        rounding=ROUND_FLOOR
    )

    if whole_share_quantity >= 1:
        return EquityEntryExecutionPlan(
            symbol=proposal.symbol,
            mode=(
                EquityEntryExecutionMode
                .WHOLE_SHARE_LIMIT
            ),
            budget=proposal.budget,
            quantity=whole_share_quantity,
            limit_price=quote.ask,
            quote_observed_at=(
                quote.observed_at
            ),
        )

    return EquityEntryExecutionPlan(
        symbol=proposal.symbol,
        mode=(
            EquityEntryExecutionMode
            .FRACTIONAL_MARKET
        ),
        budget=proposal.budget,
        dollar_amount=proposal.budget,
        quote_observed_at=quote.observed_at,
    )