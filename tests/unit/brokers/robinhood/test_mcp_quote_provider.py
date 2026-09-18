import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
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

class FakeMCPInvoker:
    def __init__(
        self,
        payload,
    ) -> None:
        self.payload = payload
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        return self.payload

class MCPRobinhoodEquityQuoteProviderTests(
    unittest.TestCase
):
    def test_get_quote_calls_robinhood_mcp(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            make_payload()
        )

        provider = (
            MCPRobinhoodEquityQuoteProvider(
                invoker
            )
        )

        quote = provider.get_quote(
            " aapl "
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
            invoker.calls,
            [
                (
                    "get_equity_quotes",
                    {
                        "symbols": [
                            "AAPL",
                        ],
                    },
                )
            ],
        )

    def test_empty_symbol_is_rejected_before_mcp(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            make_payload()
        )

        provider = (
            MCPRobinhoodEquityQuoteProvider(
                invoker
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "symbol",
        ):
            provider.get_quote("   ")

        self.assertEqual(
            invoker.calls,
            [],
        )