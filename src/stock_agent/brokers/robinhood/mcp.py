from typing import Any, Protocol


class MCPToolInvocationUncertainError(RuntimeError):
    pass

class MCPToolInvocationNotSentError(RuntimeError):
    """The transport can prove the request was not sent."""


class MCPToolInvoker(Protocol):
    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...