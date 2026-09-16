from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvocationNotSentError,
    MCPToolInvoker,
)


class RobinhoodAccountNotAllowedError(
    MCPToolInvocationNotSentError
):
    pass


class RobinhoodAccountGuardedMCPToolInvoker:
    def __init__(
        self,
        invoker: MCPToolInvoker,
        *,
        allowed_account_number: str,
    ) -> None:
        if not isinstance(
            allowed_account_number,
            str,
        ):
            raise TypeError(
                "allowed_account_number must be a string"
            )

        if not allowed_account_number.strip():
            raise ValueError(
                "allowed_account_number cannot be empty"
            )

        self._invoker = invoker
        self._allowed_account_number = (
            allowed_account_number
        )

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        if tool_name == "get_accounts":
            raise RobinhoodAccountNotAllowedError(
                "get_accounts is blocked by "
                "the local account guard"
            )

        if "account_number" in arguments:
            account_number = arguments[
                "account_number"
            ]

            if (
                account_number
                != self._allowed_account_number
            ):
                raise RobinhoodAccountNotAllowedError(
                    "Robinhood tool call blocked: "
                    "account is not allowlisted"
                )

        return self._invoker.call_tool(
            tool_name,
            arguments,
        )