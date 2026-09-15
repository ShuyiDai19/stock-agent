from typing import Any, Protocol


class MCPToolInvocationUncertainError(RuntimeError):
    pass


class MCPToolInvocationNotSentError(RuntimeError):
    pass


class MCPToolExecutionError(RuntimeError):
    pass


class MCPToolResultShapeError(RuntimeError):
    pass


class MCPToolInvoker(Protocol):
    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...


class MCPCallToolResult(Protocol):
    @property
    def is_error(self) -> bool:
        ...

    @property
    def structured_content(
        self,
    ) -> Any:
        ...


def normalize_mcp_tool_result(
    result: MCPCallToolResult,
) -> dict[str, Any]:
    if result.is_error:
        raise MCPToolExecutionError(
            "MCP tool returned an error result"
        )

    structured_content = (
        result.structured_content
    )

    if structured_content is None:
        raise MCPToolResultShapeError(
            "MCP tool result is missing "
            "structured_content"
        )

    if not isinstance(
        structured_content,
        dict,
    ):
        raise MCPToolResultShapeError(
            "MCP tool structured_content "
            "must be an object"
        )

    return structured_content