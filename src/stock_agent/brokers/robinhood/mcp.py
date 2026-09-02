from typing import Any, Protocol


class MCPToolInvocationUncertainError(RuntimeError):
    pass


class MCPToolInvoker(Protocol):
    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...