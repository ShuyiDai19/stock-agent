from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal, InvalidOperation
from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.strategy.candidate_generation import (
    EquityCandidateMarketData,
)


_FIVE_MINUTES = timedelta(
    minutes=5
)


@dataclass(frozen=True, slots=True)
class RobinhoodCandidateQuote:
    symbol: str
    last_trade_price: Decimal
    last_trade_at: datetime
    bid: Decimal
    ask: Decimal
    quote_observed_at: datetime


@dataclass(frozen=True, slots=True)
class RobinhoodFiveMinuteBar:
    symbol: str
    begins_at: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int

    @property
    def ends_at(
        self,
    ) -> datetime:
        return (
            self.begins_at
            + _FIVE_MINUTES
        )


def _parse_positive_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if value is None:
        raise ValueError(
            f"{field_name} is missing"
        )

    try:
        parsed = Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field_name} is invalid"
        ) from exc

    if not parsed.is_finite():
        raise ValueError(
            f"{field_name} must be finite"
        )

    if parsed <= 0:
        raise ValueError(
            f"{field_name} must be "
            "greater than zero"
        )

    return parsed


def _parse_timestamp(
    value: Any,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{field_name} is missing"
        )

    try:
        parsed = (
            datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )
        )
    except ValueError as exc:
        raise ValueError(
            f"{field_name} is invalid"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be "
            "timezone-aware"
        )

    return parsed


def _to_utc_rfc3339(
    value: datetime,
) -> str:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "timestamp must be timezone-aware"
        )

    return (
        value.astimezone(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def decode_robinhood_candidate_quote(
    raw_result: Any,
    *,
    symbol: str,
) -> RobinhoodCandidateQuote:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood quote result "
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
            "Robinhood quote result "
            "must contain data"
        )

    results = data.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):
        raise ValueError(
            "Robinhood quote result "
            "must contain results"
        )

    matching = []

    for result in results:
        if not isinstance(
            result,
            dict,
        ):
            raise ValueError(
                "Robinhood quote entry "
                "must be a mapping"
            )

        quote = result.get(
            "quote"
        )

        if not isinstance(
            quote,
            dict,
        ):
            raise ValueError(
                "Robinhood quote entry "
                "must contain quote"
            )

        if quote.get(
            "symbol"
        ) == symbol:
            matching.append(
                quote
            )

    if len(matching) != 1:
        raise ValueError(
            "Robinhood quote result must "
            "contain exactly one matching symbol"
        )

    quote = matching[0]

    if quote.get(
        "has_traded"
    ) is not True:
        raise ValueError(
            "Robinhood quote has not traded"
        )

    last_trade_price = (
        _parse_positive_decimal(
            quote.get(
                "last_trade_price"
            ),
            field_name=(
                "last_trade_price"
            ),
        )
    )

    last_trade_at = (
        _parse_timestamp(
            quote.get(
                "venue_last_trade_time"
            ),
            field_name=(
                "venue_last_trade_time"
            ),
        )
    )

    bid = _parse_positive_decimal(
        quote.get(
            "bid_price"
        ),
        field_name="bid_price",
    )

    ask = _parse_positive_decimal(
        quote.get(
            "ask_price"
        ),
        field_name="ask_price",
    )

    if ask < bid:
        raise ValueError(
            "Robinhood ask cannot be "
            "below bid"
        )

    bid_at = _parse_timestamp(
        quote.get(
            "venue_bid_time"
        ),
        field_name=(
            "venue_bid_time"
        ),
    )

    ask_at = _parse_timestamp(
        quote.get(
            "venue_ask_time"
        ),
        field_name=(
            "venue_ask_time"
        ),
    )

    return RobinhoodCandidateQuote(
        symbol=symbol,
        last_trade_price=(
            last_trade_price
        ),
        last_trade_at=last_trade_at,
        bid=bid,
        ask=ask,
        # Both sides must be fresh, so use
        # the older side of the market.
        quote_observed_at=min(
            bid_at,
            ask_at,
        ),
    )


def decode_robinhood_five_minute_bars(
    raw_result: Any,
    *,
    symbol: str,
) -> tuple[
    RobinhoodFiveMinuteBar,
    ...,
]:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood historical result "
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
            "Robinhood historical result "
            "must contain data"
        )

    results = data.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):
        raise ValueError(
            "Robinhood historical result "
            "must contain results"
        )

    matching = [
        result
        for result in results
        if (
            isinstance(
                result,
                dict,
            )
            and result.get(
                "symbol"
            ) == symbol
        )
    ]

    if len(matching) != 1:
        raise ValueError(
            "Robinhood historical result "
            "must contain exactly one "
            "matching symbol"
        )

    result = matching[0]

    if result.get(
        "interval"
    ) != "5minute":
        raise ValueError(
            "Robinhood historical interval "
            "must be 5minute"
        )

    if result.get(
        "bounds"
    ) != "regular":
        raise ValueError(
            "Robinhood historical bounds "
            "must be regular"
        )

    raw_bars = result.get(
        "bars"
    )

    if not isinstance(
        raw_bars,
        list,
    ):
        raise ValueError(
            "Robinhood historical result "
            "must contain bars"
        )

    bars = []

    for raw_bar in raw_bars:
        if not isinstance(
            raw_bar,
            dict,
        ):
            raise ValueError(
                "Robinhood historical bar "
                "must be a mapping"
            )

        volume = raw_bar.get(
            "volume"
        )

        if (
            type(volume) is not int
            or volume < 0
        ):
            raise ValueError(
                "bar volume must be a "
                "non-negative integer"
            )

        bars.append(
            RobinhoodFiveMinuteBar(
                symbol=symbol,
                begins_at=(
                    _parse_timestamp(
                        raw_bar.get(
                            "begins_at"
                        ),
                        field_name=(
                            "begins_at"
                        ),
                    )
                ),
                open_price=(
                    _parse_positive_decimal(
                        raw_bar.get(
                            "open_price"
                        ),
                        field_name=(
                            "open_price"
                        ),
                    )
                ),
                high_price=(
                    _parse_positive_decimal(
                        raw_bar.get(
                            "high_price"
                        ),
                        field_name=(
                            "high_price"
                        ),
                    )
                ),
                low_price=(
                    _parse_positive_decimal(
                        raw_bar.get(
                            "low_price"
                        ),
                        field_name=(
                            "low_price"
                        ),
                    )
                ),
                close_price=(
                    _parse_positive_decimal(
                        raw_bar.get(
                            "close_price"
                        ),
                        field_name=(
                            "close_price"
                        ),
                    )
                ),
                volume=volume,
            )
        )

    bars.sort(
        key=lambda bar: (
            bar.begins_at
        )
    )

    if len(
        {
            bar.begins_at
            for bar in bars
        }
    ) != len(bars):
        raise ValueError(
            "Robinhood historical bars "
            "contain duplicate timestamps"
        )

    return tuple(
        bars
    )


def calculate_completed_bar_vwap(
    bars: tuple[
        RobinhoodFiveMinuteBar,
        ...,
    ],
) -> Decimal:
    total_volume = sum(
        bar.volume
        for bar in bars
    )

    if total_volume <= 0:
        raise ValueError(
            "VWAP requires positive "
            "total volume"
        )

    weighted_total = Decimal(
        "0"
    )

    for bar in bars:
        typical_price = (
            bar.high_price
            + bar.low_price
            + bar.close_price
        ) / Decimal("3")

        weighted_total += (
            typical_price
            * Decimal(
                bar.volume
            )
        )

    return (
        weighted_total
        / Decimal(
            total_volume
        )
    )


def build_candidate_market_data_from_robinhood(
    *,
    quote: RobinhoodCandidateQuote,
    bars: tuple[
        RobinhoodFiveMinuteBar,
        ...,
    ],
    evaluated_at: datetime,
) -> EquityCandidateMarketData:
    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be "
            "timezone-aware"
        )

    completed_bars = tuple(
        bar
        for bar in bars
        if (
            bar.ends_at
            <= evaluated_at
        )
    )

    if len(
        completed_bars
    ) < 3:
        raise ValueError(
            "candidate generation requires "
            "at least three completed "
            "5-minute bars"
        )

    if any(
        bar.symbol != quote.symbol
        for bar in completed_bars
    ):
        raise ValueError(
            "historical symbol must "
            "match quote symbol"
        )

    return EquityCandidateMarketData(
        symbol=quote.symbol,
        price=(
            quote.last_trade_price
        ),
        session_open=(
            completed_bars[
                0
            ].open_price
        ),
        vwap=(
            calculate_completed_bar_vwap(
                completed_bars
            )
        ),
        recent_5m_closes=(
            completed_bars[-3]
            .close_price,
            completed_bars[-2]
            .close_price,
            completed_bars[-1]
            .close_price,
        ),
        bid=quote.bid,
        ask=quote.ask,
        signal_observed_at=(
            quote.last_trade_at
        ),
        quote_observed_at=(
            quote.quote_observed_at
        ),
    )


def load_robinhood_equity_candidate_market_data(
    invoker: MCPToolInvoker,
    *,
    symbol: str,
    session_start: datetime,
    evaluated_at: datetime,
) -> EquityCandidateMarketData:
    if not symbol.strip():
        raise ValueError(
            "symbol cannot be empty"
        )

    if symbol != symbol.upper():
        raise ValueError(
            "symbol must be uppercase"
        )

    if (
        session_start.tzinfo is None
        or session_start.utcoffset()
        is None
    ):
        raise ValueError(
            "session_start must be "
            "timezone-aware"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset()
        is None
    ):
        raise ValueError(
            "evaluated_at must be "
            "timezone-aware"
        )

    if session_start >= evaluated_at:
        raise ValueError(
            "session_start must be "
            "before evaluated_at"
        )

    quote_raw = invoker.call_tool(
        "get_equity_quotes",
        {
            "symbols": [
                symbol,
            ],
        },
    )

    historical_raw = invoker.call_tool(
        "get_equity_historicals",
        {
            "symbols": [
                symbol,
            ],
            "start_time": (
                _to_utc_rfc3339(
                    session_start
                )
            ),
            "end_time": (
                _to_utc_rfc3339(
                    evaluated_at
                )
            ),
            "interval": "5minute",
            "bounds": "regular",
            "adjustment_type": "split",
        },
    )

    quote = (
        decode_robinhood_candidate_quote(
            quote_raw,
            symbol=symbol,
        )
    )

    bars = (
        decode_robinhood_five_minute_bars(
            historical_raw,
            symbol=symbol,
        )
    )

    return (
        build_candidate_market_data_from_robinhood(
            quote=quote,
            bars=bars,
            evaluated_at=(
                evaluated_at
            ),
        )
    )