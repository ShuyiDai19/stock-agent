import asyncio
import unittest

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvocationNotSentError,
    MCPToolInvocationUncertainError,
)
from stock_agent.brokers.robinhood.persistent_mcp_invoker import (
    PersistentMCPToolInvoker,
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
        self.server = server
        self.calls = []
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.exited = True

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

    async def list_tools(
        self,
    ):
        return {
            "tools": [
                {
                    "name": "get_equity_orders",
                },
                {
                    "name": "get_option_orders",
                },
            ]
        }

class SlowFakeMCPClient(
    FakeMCPClient
):
    async def call_tool(
        self,
        tool_name,
        arguments,
    ):
        await asyncio.sleep(
            1.0
        )

        return FakeCallToolResult(
            {
                "data": {}
            }
        )

class PersistentMCPToolInvokerTests(
    unittest.TestCase
):
    def test_calls_tool_through_persistent_client(
        self,
    ) -> None:
        clients = []

        def factory(server):
            client = FakeMCPClient(server)
            clients.append(client)
            return client

        with PersistentMCPToolInvoker(
            "fake-server",
            client_factory=factory,
        ) as invoker:
            first = invoker.call_tool(
                "get_equity_orders",
                {
                    "account_number": "account-test",
                },
            )

            second = invoker.call_tool(
                "get_option_orders",
                {
                    "account_number": "account-test",
                },
            )

            self.assertEqual(
                first,
                {
                    "data": {
                        "orders": [],
                    }
                },
            )

            self.assertEqual(
                second,
                {
                    "data": {
                        "orders": [],
                    }
                },
            )

            self.assertEqual(
                len(clients),
                1,
            )

            self.assertTrue(
                clients[0].entered
            )

            self.assertEqual(
                len(clients[0].calls),
                2,
            )

        self.assertTrue(
            clients[0].exited
        )

    def test_call_before_start_is_definitely_not_sent(
        self,
    ) -> None:
        invoker = PersistentMCPToolInvoker(
            "fake-server",
            client_factory=FakeMCPClient,
        )

        with self.assertRaises(
            MCPToolInvocationNotSentError
        ):
            invoker.call_tool(
                "get_equity_orders",
                {},
            )

    def test_tool_timeout_is_uncertain(
        self,
    ) -> None:
        with PersistentMCPToolInvoker(
            "fake-server",
            client_factory=SlowFakeMCPClient,
            call_timeout_seconds=0.01,
        ) as invoker:
            with self.assertRaises(
                MCPToolInvocationUncertainError
            ):
                invoker.call_tool(
                    "place_equity_order",
                    {
                        "symbol": "AAPL",
                    },
                )

    def test_lists_tools_through_persistent_client(
        self,
    ) -> None:
        clients = []

        def factory(server):
            client = FakeMCPClient(server)
            clients.append(client)
            return client

        with PersistentMCPToolInvoker(
            "https://example.com/mcp",
            client_factory=factory,
        ) as invoker:
            result = invoker.list_tools()

        self.assertEqual(
            result,
            {
                "tools": [
                    {
                        "name": "get_equity_orders",
                    },
                    {
                        "name": "get_option_orders",
                    },
                ]
            },
        )

        self.assertEqual(
            len(clients),
            1,
        )