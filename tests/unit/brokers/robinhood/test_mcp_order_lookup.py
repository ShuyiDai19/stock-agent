import unittest
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


class MCPRobinhoodOrderLookupTests(unittest.TestCase):
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
                    ]
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
                    ]
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