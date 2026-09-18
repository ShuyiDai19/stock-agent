import unittest
from datetime import timezone
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp_quote_decoder import (
    RobinhoodQuoteDecodeError,
    decode_robinhood_equity_quote,
)


def make_payload():
    return {
        "data": {
            "results": [
                {
                    "quote": {
                        "symbol": "AAPL",
                        "last_trade_price":
                            "337.080000",
                        "venue_last_trade_time":
                            (
                                "2026-09-17T19:59:"
                                "59.837226061Z"
                            ),
                        "bid_price":
                            "336.210000",
                        "venue_bid_time":
                            (
                                "2026-09-17T23:49:"
                                "07.69164658Z"
                            ),
                        "ask_price":
                            "336.260000",
                        "venue_ask_time":
                            (
                                "2026-09-17T23:49:"
                                "07.69164658Z"
                            ),
                        "has_traded": True,
                        "state": "active",
                    },
                    "close": {
                        "symbol": "AAPL",
                        "date": "2026-09-16",
                        "price": "332.41",
                        "interpolated": False,
                        "source":
                            "sip-list-exchange-close",
                    },
                }
            ]
        }
    }


class RobinhoodQuoteDecoderTests(
    unittest.TestCase
):
    def test_decodes_executable_bid(
        self,
    ) -> None:
        quote = (
            decode_robinhood_equity_quote(
                make_payload(),
                expected_symbol="AAPL",
            )
        )

        self.assertEqual(
            quote.symbol,
            "AAPL",
        )

        self.assertEqual(
            quote.bid,
            Decimal("336.210000"),
        )

        self.assertEqual(
            quote.observed_at.tzinfo,
            timezone.utc,
        )

        self.assertEqual(
            quote.observed_at.hour,
            23,
        )

        self.assertEqual(
            quote.observed_at.minute,
            49,
        )

        self.assertEqual(
            quote.observed_at.second,
            7,
        )

    def test_uses_bid_not_last_trade(
        self,
    ) -> None:
        payload = make_payload()

        payload["data"]["results"][0][
            "quote"
        ]["last_trade_price"] = "999.00"

        quote = (
            decode_robinhood_equity_quote(
                payload,
                expected_symbol="AAPL",
            )
        )

        self.assertEqual(
            quote.bid,
            Decimal("336.210000"),
        )

    def test_rejects_inactive_quote(
        self,
    ) -> None:
        payload = make_payload()

        payload["data"]["results"][0][
            "quote"
        ]["state"] = "inactive"

        with self.assertRaisesRegex(
            RobinhoodQuoteDecodeError,
            "not active",
        ):
            decode_robinhood_equity_quote(
                payload,
                expected_symbol="AAPL",
            )

    def test_rejects_zero_bid(
        self,
    ) -> None:
        payload = make_payload()

        payload["data"]["results"][0][
            "quote"
        ]["bid_price"] = "0"

        with self.assertRaisesRegex(
            RobinhoodQuoteDecodeError,
            "greater than zero",
        ):
            decode_robinhood_equity_quote(
                payload,
                expected_symbol="AAPL",
            )

    def test_rejects_symbol_mismatch(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            RobinhoodQuoteDecodeError,
            "does not match",
        ):
            decode_robinhood_equity_quote(
                make_payload(),
                expected_symbol="MSFT",
            )