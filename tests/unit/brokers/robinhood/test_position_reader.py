import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood.position_reader import (
    MCPRobinhoodEquityPositionReader,
    RobinhoodPositionPaginationError,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionType,
)


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

class SequencedFakeMCPInvoker:
    def __init__(
        self,
        payloads,
    ) -> None:
        self.payloads = list(
            payloads
        )
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

        if not self.payloads:
            raise AssertionError(
                "unexpected extra MCP call"
            )

        return self.payloads.pop(0)

class MCPRobinhoodEquityPositionReaderTests(
    unittest.TestCase
):
    def test_reads_equity_positions(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "data": {
                    "positions": [
                        {
                            "symbol": "AAPL",
                            "quantity": "0.031089",
                            "intraday_quantity":
                                "0.000000",
                            "average_buy_price":
                                "321.660000",
                            "shares_available_for_sells":
                                "0.031089",
                            "type": "long",
                        }
                    ]
                }
            }
        )

        reader = (
            MCPRobinhoodEquityPositionReader(
                invoker
            )
        )

        result = reader.read(
            account_number=(
                "agentic-account"
            )
        )

        self.assertEqual(
            len(result.positions),
            1,
        )

        position = result.positions[0]

        self.assertEqual(
            position.symbol,
            "AAPL",
        )

        self.assertEqual(
            position.quantity,
            Decimal("0.031089"),
        )

        self.assertEqual(
            position.shares_available_for_sells,
            Decimal("0.031089"),
        )

        self.assertEqual(
            position.position_type,
            RobinhoodEquityPositionType.LONG,
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_equity_positions",
                    {
                        "account_number":
                            "agentic-account",
                    },
                )
            ],
        )

    def test_reads_empty_equity_positions(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "data": {
                    "positions": [],
                }
            }
        )

        reader = MCPRobinhoodEquityPositionReader(
            invoker
        )

        result = reader.read(
            account_number="agentic-account"
        )

        self.assertEqual(
            result.positions,
            (),
        )

    def test_rejects_empty_account_number(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "data": {
                    "positions": [],
                }
            }
        )

        reader = MCPRobinhoodEquityPositionReader(
            invoker
        )

        with self.assertRaisesRegex(
            ValueError,
            "account_number",
        ):
            reader.read(
                account_number="   "
            )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_reads_multiple_pages(
        self,
    ) -> None:
        invoker = SequencedFakeMCPInvoker(
            [
                {
                    "data": {
                        "positions": [
                            {
                                "symbol": "AAPL",
                                "quantity": "1",
                                "intraday_quantity": "0",
                                "average_buy_price": "100",
                                "shares_available_for_sells":
                                    "1",
                                "type": "long",
                            }
                        ]
                    },
                    "next": (
                        "https://example.test/"
                        "?cursor=cursor-2"
                    ),
                },
                {
                    "data": {
                        "positions": [
                            {
                                "symbol": "MSFT",
                                "quantity": "2",
                                "intraday_quantity": "0",
                                "average_buy_price": "200",
                                "shares_available_for_sells":
                                    "2",
                                "type": "long",
                            }
                        ]
                    }
                },
            ]
        )

        reader = (
            MCPRobinhoodEquityPositionReader(
                invoker
            )
        )

        result = reader.read(
            account_number="agentic-account"
        )

        self.assertEqual(
            [
                position.symbol
                for position
                in result.positions
            ],
            [
                "AAPL",
                "MSFT",
            ],
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_equity_positions",
                    {
                        "account_number":
                            "agentic-account",
                    },
                ),
                (
                    "get_equity_positions",
                    {
                        "account_number":
                            "agentic-account",
                        "cursor":
                            "cursor-2",
                    },
                ),
            ],
        )

    def test_rejects_repeated_cursor(
        self,
    ) -> None:
        payload = {
            "data": {
                "positions": [],
            },
            "next": (
                "https://example.test/"
                "?cursor=same"
            ),
        }

        invoker = (
            SequencedFakeMCPInvoker(
                [
                    payload,
                    payload,
                ]
            )
        )

        reader = (
            MCPRobinhoodEquityPositionReader(
                invoker
            )
        )

        with self.assertRaisesRegex(
            RobinhoodPositionPaginationError,
            "repeated",
        ):
            reader.read(
                account_number=(
                    "agentic-account"
                )
            )