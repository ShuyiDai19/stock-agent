from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from stock_agent.domain import QuoteSnapshot


class RobinhoodQuoteDecodeError(
    ValueError
):
    pass


def _require_dict(
    value: Any,
    *,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RobinhoodQuoteDecodeError(
            f"{field} must be an object"
        )

    return value


def _require_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise RobinhoodQuoteDecodeError(
            f"{field} must be a string"
        )

    value = value.strip()

    if not value:
        raise RobinhoodQuoteDecodeError(
            f"{field} must not be empty"
        )

    return value


def _decode_decimal(
    value: Any,
    *,
    field: str,
) -> Decimal:
    raw = _require_string(
        value,
        field=field,
    )

    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise RobinhoodQuoteDecodeError(
            f"{field} must be a decimal"
        ) from exc

    if not result.is_finite():
        raise RobinhoodQuoteDecodeError(
            f"{field} must be finite"
        )

    return result


def _decode_timestamp(
    value: Any,
    *,
    field: str,
) -> datetime:
    raw = _require_string(
        value,
        field=field,
    )

    try:
        parsed = datetime.fromisoformat(
            raw.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise RobinhoodQuoteDecodeError(
            f"{field} must be an ISO timestamp"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise RobinhoodQuoteDecodeError(
            f"{field} must be timezone-aware"
        )

    return parsed


def decode_robinhood_equity_quote(
    payload: dict[str, Any],
    *,
    expected_symbol: str,
) -> QuoteSnapshot:
    symbol = expected_symbol.strip().upper()

    if not symbol:
        raise RobinhoodQuoteDecodeError(
            "expected_symbol must not be empty"
        )

    data = _require_dict(
        payload.get("data"),
        field="data",
    )

    results = data.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):
        raise RobinhoodQuoteDecodeError(
            "data.results must be a list"
        )

    if len(results) != 1:
        raise RobinhoodQuoteDecodeError(
            "expected exactly one quote result"
        )

    result = _require_dict(
        results[0],
        field="data.results[0]",
    )

    quote = _require_dict(
        result.get("quote"),
        field="data.results[0].quote",
    )

    quote_symbol = _require_string(
        quote.get("symbol"),
        field=(
            "data.results[0].quote.symbol"
        ),
    ).upper()

    if quote_symbol != symbol:
        raise RobinhoodQuoteDecodeError(
            "quote symbol does not match "
            "requested symbol"
        )

    state = _require_string(
        quote.get("state"),
        field=(
            "data.results[0].quote.state"
        ),
    )

    if state != "active":
        raise RobinhoodQuoteDecodeError(
            f"quote state is not active: {state!r}"
        )

    has_traded = quote.get(
        "has_traded"
    )

    if has_traded is not True:
        raise RobinhoodQuoteDecodeError(
            "quote has_traded must be true"
        )

    bid = _decode_decimal(
        quote.get("bid_price"),
        field=(
            "data.results[0].quote.bid_price"
        ),
    )

    if bid <= 0:
        raise RobinhoodQuoteDecodeError(
            "bid_price must be greater than zero"
        )

    observed_at = _decode_timestamp(
        quote.get("venue_bid_time"),
        field=(
            "data.results[0].quote."
            "venue_bid_time"
        ),
    )

    try:
        return QuoteSnapshot(
            symbol=quote_symbol,
            bid=bid,
            observed_at=observed_at,
        )
    except ValueError as exc:
        raise RobinhoodQuoteDecodeError(
            f"invalid quote snapshot: {exc}"
        ) from exc