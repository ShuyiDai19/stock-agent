import unittest

from stock_agent.brokers.robinhood.account_guard import (
    RobinhoodAccountNotAllowedError,
)
from stock_agent.brokers.robinhood.connection import (
    open_robinhood_mcp_invoker,
)


class FakeCallToolResult:
    def __init__(
        self,
        structured_content,
        *,
        is_error: bool = False,
    ) -> None:
        self.structured_content = structured_content
        self.is_error = is_error


class FakeMCPClient:
    def __init__(
        self,
        server,
    ) -> None:
        self.calls = []

    async def __aenter__(
        self,
    ):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return None

    async def call_tool(
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

        return FakeCallToolResult(
            {
                "data": {
                    "orders": [],
                }
            }
        )


class RobinhoodMCPConnectionTests(
    unittest.TestCase
):
    def test_composes_transport_with_account_guard(
        self,
    ) -> None:
        clients = []

        def factory(server):
            client = FakeMCPClient(server)
            clients.append(client)
            return client

        with open_robinhood_mcp_invoker(
            allowed_account_number=(
                "agentic-account"
            ),
            client_factory=factory,
        ) as invoker:
            result = invoker.call_tool(
                "get_equity_orders",
                {
                    "account_number": (
                        "agentic-account"
                    ),
                },
            )

            self.assertEqual(
                result,
                {
                    "data": {
                        "orders": [],
                    }
                },
            )

            with self.assertRaises(
                RobinhoodAccountNotAllowedError
            ):
                invoker.call_tool(
                    "get_equity_orders",
                    {
                        "account_number": (
                            "different-account"
                        ),
                    },
                )

        self.assertEqual(
            len(clients),
            1,
        )

        self.assertEqual(
            len(clients[0].calls),
            1,
        )