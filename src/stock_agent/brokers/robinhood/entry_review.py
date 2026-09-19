from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.strategy.entry_execution import (
    DEFAULT_MAX_QUOTE_AGE,
    DEFAULT_MAX_SPREAD_RATIO,
    EntryExecutionNotAllowedError,
    EquityEntryExecutionMode,
    EquityEntryExecutionPlan,
    EquityExecutionQuote,
)


class RobinhoodEntryReviewMismatchError(
    RuntimeError
):
    pass


@dataclass(frozen=True, slots=True)
class RobinhoodEquityEntryReview:
    plan: EquityEntryExecutionPlan
    approved: bool
    order_checks: dict[str, Any]
    quote_data: dict[str, Any] | None
    market_data_disclosure: str | None


def _decimal_text(
    value: Decimal,
) -> str:
    return format(
        value,
        "f",
    )


def build_robinhood_equity_entry_review_arguments(
    plan: EquityEntryExecutionPlan,
    *,
    account_number: str,
) -> dict[str, str]:
    if not account_number.strip():
        raise ValueError(
            "account_number cannot be empty"
        )

    arguments = {
        "account_number": account_number,
        "symbol": plan.symbol,
        "side": "buy",
        "time_in_force": "gfd",
        "market_hours": "regular_hours",
    }

    if (
        plan.mode
        is EquityEntryExecutionMode
        .WHOLE_SHARE_LIMIT
    ):
        if (
            plan.quantity is None
            or plan.limit_price is None
        ):
            raise ValueError(
                "whole-share limit plan is incomplete"
            )

        arguments.update(
            {
                "type": "limit",
                "quantity": _decimal_text(
                    plan.quantity
                ),
                "limit_price": _decimal_text(
                    plan.limit_price
                ),
            }
        )

        return arguments

    if (
        plan.mode
        is EquityEntryExecutionMode
        .FRACTIONAL_MARKET
    ):
        if plan.dollar_amount is None:
            raise ValueError(
                "fractional market plan is incomplete"
            )

        arguments.update(
            {
                "type": "market",
                "dollar_amount": _decimal_text(
                    plan.dollar_amount
                ),
            }
        )

        return arguments

    raise ValueError(
        "unsupported equity entry execution mode"
    )


def _require_matching_text(
    data: dict[str, Any],
    *,
    field_name: str,
    expected: str,
) -> None:
    actual = data.get(
        field_name
    )

    if actual != expected:
        raise RobinhoodEntryReviewMismatchError(
            f"review {field_name} does not match request"
        )


def _require_matching_decimal(
    data: dict[str, Any],
    *,
    field_name: str,
    expected: Decimal,
) -> None:
    raw_value = data.get(
        field_name
    )

    if not isinstance(
        raw_value,
        str,
    ):
        raise RobinhoodEntryReviewMismatchError(
            f"review {field_name} is missing"
        )

    try:
        actual = Decimal(
            raw_value
        )
    except InvalidOperation as exc:
        raise RobinhoodEntryReviewMismatchError(
            f"review {field_name} is invalid"
        ) from exc

    if (
        not actual.is_finite()
        or actual != expected
    ):
        raise RobinhoodEntryReviewMismatchError(
            f"review {field_name} does not match request"
        )


def review_robinhood_equity_entry(
    invoker: MCPToolInvoker,
    *,
    account_number: str,
    plan: EquityEntryExecutionPlan,
) -> RobinhoodEquityEntryReview:
    arguments = (
        build_robinhood_equity_entry_review_arguments(
            plan,
            account_number=account_number,
        )
    )

    raw_result = invoker.call_tool(
        "review_equity_order",
        arguments,
    )

    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood entry review result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood entry review result "
            "must contain data"
        )

    _require_matching_text(
        data,
        field_name="symbol",
        expected=plan.symbol,
    )

    _require_matching_text(
        data,
        field_name="side",
        expected="buy",
    )

    order_checks = data.get(
        "order_checks"
    )

    if not isinstance(
        order_checks,
        dict,
    ):
        raise ValueError(
            "Robinhood entry review must "
            "contain order_checks"
        )

    if (
        plan.mode
        is EquityEntryExecutionMode
        .WHOLE_SHARE_LIMIT
    ):
        _require_matching_text(
            data,
            field_name="type",
            expected="limit",
        )

        _require_matching_decimal(
            data,
            field_name="quantity",
            expected=plan.quantity,
        )

        _require_matching_decimal(
            data,
            field_name="limit_price",
            expected=plan.limit_price,
        )

    else:
        _require_matching_text(
            data,
            field_name="type",
            expected="market",
        )

        _require_matching_decimal(
            data,
            field_name="dollar_amount",
            expected=plan.dollar_amount,
        )

    quote_data = data.get(
        "quote_data"
    )

    if (
        quote_data is not None
        and not isinstance(
            quote_data,
            dict,
        )
    ):
        raise ValueError(
            "quote_data must be a mapping"
        )

    disclosure = data.get(
        "market_data_disclosure"
    )

    if (
        disclosure is not None
        and not isinstance(
            disclosure,
            str,
        )
    ):
        raise ValueError(
            "market_data_disclosure must be a string"
        )

    return RobinhoodEquityEntryReview(
        plan=plan,
        approved=not bool(
            order_checks
        ),
        order_checks=order_checks,
        quote_data=quote_data,
        market_data_disclosure=disclosure,
    )

def _parse_review_decimal(
    quote_data: dict[str, Any],
    *,
    field_name: str,
) -> Decimal:
    raw_value = quote_data.get(
        field_name
    )

    if not isinstance(
        raw_value,
        str,
    ):
        raise EntryExecutionNotAllowedError(
            f"review quote {field_name} is missing"
        )

    try:
        value = Decimal(
            raw_value
        )
    except InvalidOperation as exc:
        raise EntryExecutionNotAllowedError(
            f"review quote {field_name} is invalid"
        ) from exc

    if (
        not value.is_finite()
        or value <= 0
    ):
        raise EntryExecutionNotAllowedError(
            f"review quote {field_name} is invalid"
        )

    return value


def _parse_review_time(
    quote_data: dict[str, Any],
    *,
    field_name: str,
) -> datetime:
    raw_value = quote_data.get(
        field_name
    )

    if not isinstance(
        raw_value,
        str,
    ):
        raise EntryExecutionNotAllowedError(
            f"review quote {field_name} is missing"
        )

    try:
        value = datetime.fromisoformat(
            raw_value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise EntryExecutionNotAllowedError(
            f"review quote {field_name} is invalid"
        ) from exc

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise EntryExecutionNotAllowedError(
            f"review quote {field_name} "
            "must be timezone-aware"
        )

    return value


def revalidate_robinhood_equity_entry_review(
    review: RobinhoodEquityEntryReview,
    *,
    evaluated_at: datetime,
    max_quote_age: timedelta = (
        DEFAULT_MAX_QUOTE_AGE
    ),
    max_spread_ratio: Decimal = (
        DEFAULT_MAX_SPREAD_RATIO
    ),
) -> EquityExecutionQuote:
    if not review.approved:
        raise EntryExecutionNotAllowedError(
            "Robinhood entry review was not approved"
        )

    quote_data = review.quote_data

    if quote_data is None:
        raise EntryExecutionNotAllowedError(
            "Robinhood entry review "
            "did not contain live quote data"
        )

    bid = _parse_review_decimal(
        quote_data,
        field_name="bid_price",
    )

    ask = _parse_review_decimal(
        quote_data,
        field_name="ask_price",
    )

    bid_at = _parse_review_time(
        quote_data,
        field_name="venue_bid_time",
    )

    ask_at = _parse_review_time(
        quote_data,
        field_name="venue_ask_time",
    )

    # Fail conservatively: the quote is only as fresh
    # as its older side.
    observed_at = min(
        bid_at,
        ask_at,
    )

    quote = EquityExecutionQuote(
        symbol=review.plan.symbol,
        bid=bid,
        ask=ask,
        observed_at=observed_at,
    )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be timezone-aware"
        )

    quote_age = (
        evaluated_at
        - quote.observed_at
    )

    if quote_age < timedelta(0):
        raise EntryExecutionNotAllowedError(
            "review quote cannot be from the future"
        )

    if quote_age > max_quote_age:
        raise EntryExecutionNotAllowedError(
            "review quote is stale"
        )

    if (
        quote.spread_ratio
        > max_spread_ratio
    ):
        raise EntryExecutionNotAllowedError(
            "review bid-ask spread exceeds "
            "entry limit"
        )

    if (
        review.plan.mode
        is EquityEntryExecutionMode
        .WHOLE_SHARE_LIMIT
    ):
        if review.plan.limit_price is None:
            raise ValueError(
                "whole-share limit plan "
                "requires limit_price"
            )

        if ask > review.plan.limit_price:
            raise EntryExecutionNotAllowedError(
                "review ask moved above "
                "entry limit price"
            )

    return quote