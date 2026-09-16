import unittest

from stock_agent.brokers.robinhood.account_guard import (
    RobinhoodAccountGuardedMCPToolInvoker,
    RobinhoodAccountNotAllowedError,
)


class FakeMCPToolInvoker:
    def __init__(self) -> None:
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

        return {
            "data": {
                "ok": True,
            }
        }

class RobinhoodAccountGuardedMCPToolInvokerTests(
    unittest.TestCase
):
    ALLOWED_ACCOUNT = "agentic-account"

    def setUp(self) -> None:
        self.inner = FakeMCPToolInvoker()

        self.invoker = (
            RobinhoodAccountGuardedMCPToolInvoker(
                self.inner,
                allowed_account_number=(
                    self.ALLOWED_ACCOUNT
                ),
            )
        )

    def test_allows_allowlisted_account(
        self,
    ) -> None:
        result = self.invoker.call_tool(
            "get_equity_orders",
            {
                "account_number": (
                    self.ALLOWED_ACCOUNT
                ),
                "placed_agent": "agentic",
            },
        )

        self.assertEqual(
            result,
            {
                "data": {
                    "ok": True,
                }
            },
        )

        self.assertEqual(
            len(self.inner.calls),
            1,
        )

    def test_blocks_non_allowlisted_account_before_mcp_call(
        self,
    ) -> None:
        with self.assertRaises(
            RobinhoodAccountNotAllowedError
        ):
            self.invoker.call_tool(
                "get_equity_orders",
                {
                    "account_number": (
                        "different-account"
                    ),
                },
            )

        self.assertEqual(
            self.inner.calls,
            [],
        )

    def test_blocks_place_for_non_allowlisted_account_before_mcp_call(
        self,
    ) -> None:
        with self.assertRaises(
            RobinhoodAccountNotAllowedError
        ):
            self.invoker.call_tool(
                "place_equity_order",
                {
                    "account_number": (
                        "different-account"
                    ),
                    "symbol": "AAPL",
                    "side": "sell",
                    "type": "market",
                    "quantity": "0.01",
                },
            )

        self.assertEqual(
            self.inner.calls,
            [],
        )

    def test_blocks_get_accounts(
        self,
    ) -> None:
        with self.assertRaises(
            RobinhoodAccountNotAllowedError
        ):
            self.invoker.call_tool(
                "get_accounts",
                {},
            )

        self.assertEqual(
            self.inner.calls,
            [],
        )

    def test_allows_non_account_scoped_tool(
        self,
    ) -> None:
        self.invoker.call_tool(
            "get_equity_quotes",
            {
                "symbols": [
                    "AAPL",
                ],
            },
        )

        self.assertEqual(
            len(self.inner.calls),
            1,
        )

        self.assertEqual(
            self.inner.calls[0][0],
            "get_equity_quotes",
        )

    def test_rejects_empty_allowed_account(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cannot be empty",
        ):
            RobinhoodAccountGuardedMCPToolInvoker(
                self.inner,
                allowed_account_number="",
            )