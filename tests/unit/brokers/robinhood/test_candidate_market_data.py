import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import Any

from stock_agent.brokers.robinhood.candidate_market_data import (
    build_candidate_market_data_from_robinhood,
    calculate_completed_bar_vwap,
    decode_robinhood_candidate_quote,
    decode_robinhood_five_minute_bars,
    load_robinhood_equity_candidate_market_data,
)


_SESSION_START = datetime(
    2026,
    9,
    18,
    13,
    30,
    tzinfo=timezone.utc,
)

_EVALUATED_AT = datetime(
    2026,
    9,
    18,
    13,
    47,
    tzinfo=timezone.utc,
)


def quote_payload(
) -> dict:
    return {
        "data": {
            "results": [
                {
                    "quote": {
                        "symbol": "AAPL",
                        "last_trade_price": (
                            "101.20"
                        ),
                        "venue_last_trade_time": (
                            "2026-09-18"
                            "T13:46:59Z"
                        ),
                        "bid_price": (
                            "101.18"
                        ),
                        "venue_bid_time": (
                            "2026-09-18"
                            "T13:46:58Z"
                        ),
                        "ask_price": (
                            "101.22"
                        ),
                        "venue_ask_time": (
                            "2026-09-18"
                            "T13:46:59Z"
                        ),
                        "has_traded": True,
                        "state": "active",
                    }
                }
            ]
        }
    }


def historical_payload(
) -> dict:
    return {
        "data": {
            "results": [
                {
                    "symbol": "AAPL",
                    "interval": "5minute",
                    "bounds": "regular",
                    "bars": [
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:30:00Z"
                            ),
                            "open_price": "100",
                            "high_price": "101",
                            "low_price": "99",
                            "close_price": "100",
                            "volume": 100,
                            "session": "reg",
                        },
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:35:00Z"
                            ),
                            "open_price": "100",
                            "high_price": "102",
                            "low_price": "100",
                            "close_price": "101",
                            "volume": 200,
                            "session": "reg",
                        },
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:40:00Z"
                            ),
                            "open_price": "101",
                            "high_price": "103",
                            "low_price": "101",
                            "close_price": "102",
                            "volume": 300,
                            "session": "reg",
                        },

                        # This bar is still incomplete at
                        # 13:47 and must not enter signal/VWAP.
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:45:00Z"
                            ),
                            "open_price": "102",
                            "high_price": "110",
                            "low_price": "90",
                            "close_price": "109",
                            "volume": 999999,
                            "session": "reg",
                        },
                    ],
                }
            ]
        }
    }


class FakeInvoker:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        if tool_name == (
            "get_equity_quotes"
        ):
            return quote_payload()

        if tool_name == (
            "get_equity_historicals"
        ):
            return historical_payload()

        raise AssertionError(
            f"unexpected tool: {tool_name}"
        )


class CandidateMarketDataTests(
    unittest.TestCase
):
    def test_decodes_candidate_quote(
        self,
    ) -> None:
        quote = (
            decode_robinhood_candidate_quote(
                quote_payload(),
                symbol="AAPL",
            )
        )

        self.assertEqual(
            quote.last_trade_price,
            Decimal("101.20"),
        )

        self.assertEqual(
            quote.bid,
            Decimal("101.18"),
        )

        self.assertEqual(
            quote.ask,
            Decimal("101.22"),
        )

        # Older side wins.
        self.assertEqual(
            quote.quote_observed_at,
            datetime(
                2026,
                9,
                18,
                13,
                46,
                58,
                tzinfo=timezone.utc,
            ),
        )

    def test_decodes_five_minute_bars(
        self,
    ) -> None:
        bars = (
            decode_robinhood_five_minute_bars(
                historical_payload(),
                symbol="AAPL",
            )
        )

        self.assertEqual(
            len(bars),
            4,
        )

        self.assertEqual(
            bars[0].open_price,
            Decimal("100"),
        )

        self.assertEqual(
            bars[2].close_price,
            Decimal("102"),
        )

        self.assertEqual(
            bars[2].volume,
            300,
        )

    def test_vwap_uses_typical_price_and_volume(
        self,
    ) -> None:
        bars = (
            decode_robinhood_five_minute_bars(
                historical_payload(),
                symbol="AAPL",
            )
        )[:3]

        vwap = (
            calculate_completed_bar_vwap(
                bars
            )
        )

        expected = (
            (
                Decimal("100")
                * Decimal("100")
            )
            + (
                Decimal("101")
                * Decimal("200")
            )
            + (
                Decimal("102")
                * Decimal("300")
            )
        ) / Decimal("600")

        self.assertEqual(
            vwap,
            expected,
        )

    def test_incomplete_bar_is_excluded(
        self,
    ) -> None:
        quote = (
            decode_robinhood_candidate_quote(
                quote_payload(),
                symbol="AAPL",
            )
        )

        bars = (
            decode_robinhood_five_minute_bars(
                historical_payload(),
                symbol="AAPL",
            )
        )

        data = (
            build_candidate_market_data_from_robinhood(
                quote=quote,
                bars=bars,
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            data.session_open,
            Decimal("100"),
        )

        self.assertEqual(
            data.recent_5m_closes,
            (
                Decimal("100"),
                Decimal("101"),
                Decimal("102"),
            ),
        )

        self.assertNotEqual(
            data.vwap,
            Decimal("109"),
        )

    def test_loader_calls_read_only_robinhood_tools(
        self,
    ) -> None:
        invoker = FakeInvoker()

        data = (
            load_robinhood_equity_candidate_market_data(
                invoker,
                symbol="AAPL",
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            data.symbol,
            "AAPL",
        )

        self.assertEqual(
            [
                call[0]
                for call in invoker.calls
            ],
            [
                "get_equity_quotes",
                "get_equity_historicals",
            ],
        )

        self.assertEqual(
            invoker.calls[0][1],
            {
                "symbols": [
                    "AAPL"
                ]
            },
        )

        historical_args = (
            invoker.calls[1][1]
        )

        self.assertEqual(
            historical_args[
                "interval"
            ],
            "5minute",
        )

        self.assertEqual(
            historical_args[
                "bounds"
            ],
            "regular",
        )

        self.assertEqual(
            historical_args[
                "adjustment_type"
            ],
            "split",
        )

    def test_requires_three_completed_bars(
        self,
    ) -> None:
        quote = (
            decode_robinhood_candidate_quote(
                quote_payload(),
                symbol="AAPL",
            )
        )

        bars = (
            decode_robinhood_five_minute_bars(
                historical_payload(),
                symbol="AAPL",
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "at least three completed",
        ):
            build_candidate_market_data_from_robinhood(
                quote=quote,
                bars=bars,
                evaluated_at=(
                    _SESSION_START
                    + timedelta(
                        minutes=12
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()