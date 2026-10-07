import unittest

from stock_agent.brokers.robinhood.restricted_mcp_invoker import (
    MCPToolNotAllowedError,
    RestrictedMCPToolInvoker,
)


class RecordingInvoker:
    def __init__(
        self,
    ) -> None:
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
            "ok": True,
        }


class RestrictedMCPToolInvokerTests(
    unittest.TestCase
):
    def test_allowed_tool_is_delegated(
        self,
    ) -> None:
        underlying = RecordingInvoker()

        invoker = RestrictedMCPToolInvoker(
            underlying,
            allowed_tools={
                "get_equity_orders",
            },
        )

        result = invoker.call_tool(
            "get_equity_orders",
            {
                "account_number":
                    "agentic-account",
            },
        )

        self.assertEqual(
            result,
            {
                "ok": True,
            },
        )

        self.assertEqual(
            underlying.calls,
            [
                (
                    "get_equity_orders",
                    {
                        "account_number":
                            "agentic-account",
                    },
                ),
            ],
        )

    def test_disallowed_tool_fails_before_delegation(
        self,
    ) -> None:
        underlying = RecordingInvoker()

        invoker = RestrictedMCPToolInvoker(
            underlying,
            allowed_tools={
                "get_equity_orders",
            },
        )

        with self.assertRaises(
            MCPToolNotAllowedError
        ) as context:
            invoker.call_tool(
                "place_equity_order",
                {
                    "account_number":
                        "agentic-account",
                },
            )

        self.assertEqual(
            context.exception.tool_name,
            "place_equity_order",
        )

        self.assertEqual(
            underlying.calls,
            [],
        )

    def test_empty_capability_blocks_every_tool(
        self,
    ) -> None:
        underlying = RecordingInvoker()

        invoker = RestrictedMCPToolInvoker(
            underlying,
            allowed_tools=(),
        )

        with self.assertRaises(
            MCPToolNotAllowedError
        ):
            invoker.call_tool(
                "get_equity_orders",
                {},
            )

        self.assertEqual(
            underlying.calls,
            [],
        )

    def test_allowed_tools_are_exposed_as_frozen_set(
        self,
    ) -> None:
        invoker = RestrictedMCPToolInvoker(
            RecordingInvoker(),
            allowed_tools=[
                "get_equity_orders",
                "get_equity_orders",
            ],
        )

        self.assertEqual(
            invoker.allowed_tools,
            frozenset(
                {
                    "get_equity_orders",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()