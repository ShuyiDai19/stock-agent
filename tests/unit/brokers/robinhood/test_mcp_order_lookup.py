import unittest
from datetime import datetime, timezone
from typing import Any

from stock_agent.brokers.robinhood import (
    MCPRobinhoodOrderLookup,
    PlacementReconciliationRequest,
    RobinhoodOrderLookupStatus,
    build_robinhood_mcp_order_lookup_call,
    decode_robinhood_mcp_order_lookup,
)
from stock_agent.domain import AssetType


class FakeMCPToolInvoker:
    def __init__(
        self,
        result: Any,
    ) -> None:
        self.result = result
        self.call_count = 0
        self.received_tool_name = None
        self.received_arguments = None

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.call_count += 1
        self.received_tool_name = tool_name
        self.received_arguments = arguments
        return self.result


class SequencedFakeMCPToolInvoker:
    def __init__(
        self,
        results: list[Any],
    ) -> None:
        self.results = list(results)
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append(
            (tool_name, dict(arguments))
        )

        if not self.results:
            raise RuntimeError(
                "fake MCP result sequence exhausted"
            )

        return self.results.pop(0)


class MCPRobinhoodOrderLookupTests(
    unittest.TestCase
):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    def make_equity_request(
        self,
    ) -> PlacementReconciliationRequest:
        return PlacementReconciliationRequest(
            position_id="position-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            ref_id=self.REF_ID,
            option_id=None,
            placement_attempted_at=datetime(
                2026,
                9,
                2,
                4,
                40,
                tzinfo=timezone.utc,
            ),
        )

    def test_builds_equity_lookup_call(
        self,
    ) -> None:
        call = build_robinhood_mcp_order_lookup_call(
            self.make_equity_request()
        )

        self.assertEqual(
            call.tool_name,
            "get_equity_orders",
        )

        self.assertEqual(
            call.arguments,
            {
                "account_number": "account-0000",
                "symbol": "AAPL",
                "placed_agent": "agentic",
            },
        )

    def test_returns_found_for_exact_ref_id_match(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [
                        {
                            "id": "broker-order-123",
                            "symbol": "AAPL",
                            "ref_id": self.REF_ID,
                        }
                    ],
                    "next": None,
                }
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.FOUND,
        )

        self.assertEqual(
            result.broker_order_id,
            "broker-order-123",
        )

    def test_returns_not_found_for_empty_orders(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [],
                    "next": None,
                }
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.NOT_FOUND,
        )

    def test_returns_unknown_when_orders_lack_ref_id(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [
                        {
                            "id": "broker-order-123",
                            "symbol": "AAPL",
                            "side": "sell",
                            "type": "market",
                            "quantity": "0.031",
                        }
                    ],
                    "next": None,
                }
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

        self.assertIsNone(
            result.broker_order_id,
        )

        self.assertIn(
            "does not provide an exact ref_id match",
            result.message,
        )

    def test_lookup_invokes_mcp_and_decodes_result(
        self,
    ) -> None:
        request = self.make_equity_request()

        invoker = FakeMCPToolInvoker(
            {
                "data": {
                    "orders": [],
                    "next": None,
                }
            }
        )

        lookup = MCPRobinhoodOrderLookup(
            invoker
        )

        result = lookup.lookup(
            request
        )

        self.assertEqual(
            invoker.call_count,
            1,
        )

        self.assertEqual(
            invoker.received_tool_name,
            "get_equity_orders",
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.NOT_FOUND,
        )

    def test_builds_option_lookup_call(
        self,
    ) -> None:
        request = PlacementReconciliationRequest(
            position_id="position-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            ref_id=self.REF_ID,
            placement_attempted_at=datetime(
                2026,
                9,
                2,
                4,
                40,
                tzinfo=timezone.utc,
            ),
            option_id="option-contract-123",
        )

        call = build_robinhood_mcp_order_lookup_call(
            request
        )

        self.assertEqual(
            call.tool_name,
            "get_option_orders",
        )

        self.assertEqual(
            call.arguments,
            {
                "account_number": "account-0000",
                "placed_agent": "agentic",
            },
        )

    def test_empty_page_with_next_is_unknown(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [],
                    "next": (
                        "https://example.invalid/orders"
                        "?cursor=page-2"
                    ),
                }
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

        self.assertIsNone(
            result.broker_order_id,
        )

    def test_nonmatching_page_with_next_is_unknown(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [
                        {
                            "id": "other-order",
                            "ref_id": (
                                "123e4567-e89b-12d3-a456-426614174999"
                            ),
                        }
                    ],
                    "next": (
                        "https://example.invalid/orders"
                        "?cursor=page-2"
                    ),
                }
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

    def test_top_level_next_is_also_respected(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [],
                },
                "next": (
                    "https://example.invalid/orders"
                    "?cursor=page-2"
                ),
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

    def test_exact_match_can_be_found_before_last_page(
        self,
    ) -> None:
        result = decode_robinhood_mcp_order_lookup(
            self.make_equity_request(),
            {
                "data": {
                    "orders": [
                        {
                            "id": "broker-order-123",
                            "ref_id": self.REF_ID,
                        }
                    ],
                    "next": (
                        "https://example.invalid/orders"
                        "?cursor=page-2"
                    ),
                }
            },
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.FOUND,
        )

        self.assertEqual(
            result.broker_order_id,
            "broker-order-123",
        )

    def test_reads_two_pages_before_returning_not_found(
        self,
    ) -> None:
        invoker = SequencedFakeMCPToolInvoker(
            [
                {
                    "data": {
                        "orders": [],
                        "next": (
                            "https://example.invalid/orders"
                            "?cursor=page-2"
                        ),
                    }
                },
                {
                    "data": {
                        "orders": [],
                        "next": None,
                    }
                },
            ]
        )

        lookup = MCPRobinhoodOrderLookup(
            invoker
        )

        result = lookup.lookup(
            self.make_equity_request()
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.NOT_FOUND,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertEqual(
            invoker.calls[1][1]["cursor"],
            "page-2",
        )

    def test_does_not_forget_unverified_candidates_on_earlier_page(
        self,
    ) -> None:
        invoker = SequencedFakeMCPToolInvoker(
            [
                {
                    "data": {
                        "orders": [
                            {
                                "id": "other-order",
                            }
                        ],
                        "next": (
                            "https://example.invalid/orders"
                            "?cursor=page-2"
                        ),
                    }
                },
                {
                    "data": {
                        "orders": [],
                        "next": None,
                    }
                },
            ]
        )

        result = MCPRobinhoodOrderLookup(
            invoker
        ).lookup(
            self.make_equity_request()
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

    def test_repeated_cursor_stops_pagination(
        self,
    ) -> None:
        next_url = (
            "https://example.invalid/orders"
            "?cursor=page-2"
        )

        invoker = SequencedFakeMCPToolInvoker(
            [
                {
                    "data": {
                        "orders": [],
                        "next": next_url,
                    }
                },
                {
                    "data": {
                        "orders": [],
                        "next": next_url,
                    }
                },
            ]
        )

        result = MCPRobinhoodOrderLookup(
            invoker
        ).lookup(
            self.make_equity_request()
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertIn(
            "cursor repeated",
            result.message,
        )

    def test_max_pages_stops_without_claiming_not_found(
        self,
    ) -> None:
        invoker = SequencedFakeMCPToolInvoker(
            [
                {
                    "data": {
                        "orders": [],
                        "next": (
                            "https://example.invalid/orders"
                            "?cursor=page-2"
                        ),
                    }
                },
                {
                    "data": {
                        "orders": [],
                        "next": (
                            "https://example.invalid/orders"
                            "?cursor=page-3"
                        ),
                    }
                },
            ]
        )

        result = MCPRobinhoodOrderLookup(
            invoker,
            max_pages=2,
        ).lookup(
            self.make_equity_request()
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertIn(
            "maximum page limit",
            result.message,
        )

    def test_missing_pagination_metadata_is_unknown(
        self,
    ) -> None:
        invoker = SequencedFakeMCPToolInvoker(
            [
                {
                    "data": {
                        "orders": [],
                    }
                }
            ]
        )

        result = MCPRobinhoodOrderLookup(
            invoker
        ).lookup(
            self.make_equity_request()
        )

        self.assertEqual(
            result.status,
            RobinhoodOrderLookupStatus.UNKNOWN,
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )


if __name__ == "__main__":
    unittest.main()