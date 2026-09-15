import unittest

from stock_agent.brokers.robinhood.mcp import (
    MCPToolExecutionError,
    MCPToolResultShapeError,
    normalize_mcp_tool_result,
)


class FakeMCPCallToolResult:
    def __init__(
        self,
        *,
        is_error: bool,
        structured_content,
    ) -> None:
        self.is_error = is_error
        self.structured_content = (
            structured_content
        )


class MCPToolResultNormalizationTests(
    unittest.TestCase
):
    def test_normalizes_structured_mcp_tool_result(
        self,
    ) -> None:
        result = FakeMCPCallToolResult(
            is_error=False,
            structured_content={
                "data": {
                    "orders": [],
                }
            },
        )

        normalized = (
            normalize_mcp_tool_result(
                result
            )
        )

        self.assertEqual(
            normalized,
            {
                "data": {
                    "orders": [],
                }
            },
        )

    def test_rejects_mcp_tool_error_result(
        self,
    ) -> None:
        result = FakeMCPCallToolResult(
            is_error=True,
            structured_content={
                "data": {}
            },
        )

        with self.assertRaises(
            MCPToolExecutionError
        ):
            normalize_mcp_tool_result(
                result
            )

    def test_rejects_missing_structured_content(
        self,
    ) -> None:
        result = FakeMCPCallToolResult(
            is_error=False,
            structured_content=None,
        )

        with self.assertRaisesRegex(
            MCPToolResultShapeError,
            "missing structured_content",
        ):
            normalize_mcp_tool_result(
                result
            )

    def test_rejects_non_object_structured_content(
        self,
    ) -> None:
        result = FakeMCPCallToolResult(
            is_error=False,
            structured_content=[
                {
                    "data": {}
                }
            ],
        )

        with self.assertRaisesRegex(
            MCPToolResultShapeError,
            "must be an object",
        ):
            normalize_mcp_tool_result(
                result
            )


if __name__ == "__main__":
    unittest.main()