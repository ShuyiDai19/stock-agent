from collections.abc import Iterable
from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)

ROBINHOOD_SAFE_RUNTIME_TOOLS = frozenset(
    {
        "get_equity_fundamentals",
        "get_portfolio",
        "get_equity_positions",
        "get_option_positions",
        "get_equity_orders",
        "get_option_orders",
        "get_equity_quotes",
        "get_equity_historicals",
        "review_equity_order",
    }
)


ROBINHOOD_ENTRY_PLACEMENT_TOOLS = frozenset(
    {
        "place_equity_order",
    }
)


class MCPToolNotAllowedError(
    RuntimeError
):
    def __init__(
        self,
        tool_name: str,
    ) -> None:
        self.tool_name = tool_name

        super().__init__(
            "MCP tool is not allowed by "
            f"this capability: {tool_name}"
        )


class RestrictedMCPToolInvoker:
    def __init__(
        self,
        invoker: MCPToolInvoker,
        *,
        allowed_tools: Iterable[str],
    ) -> None:
        tools = frozenset(
            allowed_tools
        )

        if any(
            (
                not isinstance(tool, str)
                or not tool.strip()
            )
            for tool in tools
        ):
            raise ValueError(
                "allowed tool names must be "
                "non-empty strings"
            )

        self._invoker = invoker
        self._allowed_tools = tools

    @property
    def allowed_tools(
        self,
    ) -> frozenset[str]:
        return self._allowed_tools

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        if tool_name not in self._allowed_tools:
            raise MCPToolNotAllowedError(
                tool_name
            )

        return self._invoker.call_tool(
            tool_name,
            arguments,
        )