from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_mapping import (
    RobinhoodMCPToolCall,
)
from stock_agent.brokers.robinhood.reconciler import (
    RobinhoodOrderLookupResult,
    RobinhoodOrderLookupStatus,
)
from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationRequest,
)
from stock_agent.domain import AssetType


def build_robinhood_mcp_order_lookup_call(
    request: PlacementReconciliationRequest,
) -> RobinhoodMCPToolCall:
    if request.asset_type is AssetType.EQUITY:
        return RobinhoodMCPToolCall(
            tool_name="get_equity_orders",
            arguments={
                "account_number": request.account_number,
                "symbol": request.symbol,
                "placed_agent": "agentic",
            },
        )

    if request.asset_type is AssetType.OPTION:
        return RobinhoodMCPToolCall(
            tool_name="get_option_orders",
            arguments={
                "account_number": request.account_number,
                "placed_agent": "agentic",
            },
        )

    raise ValueError(
        f"unsupported asset type: {request.asset_type}"
    )


def decode_robinhood_mcp_order_lookup(
    request: PlacementReconciliationRequest,
    raw_result: Any,
) -> RobinhoodOrderLookupResult:
    if not isinstance(raw_result, dict):
        raise ValueError(
            "Robinhood order lookup result must be a mapping"
        )

    data = raw_result.get("data")

    if not isinstance(data, dict):
        raise ValueError(
            "Robinhood order lookup result must contain data"
        )

    orders = data.get("orders")

    if not isinstance(orders, list):
        raise ValueError(
            "Robinhood order lookup result must contain orders"
        )

    if not orders:
        return RobinhoodOrderLookupResult(
            status=RobinhoodOrderLookupStatus.NOT_FOUND,
        )

    for order in orders:
        if not isinstance(order, dict):
            raise ValueError(
                "Robinhood order lookup orders must be mappings"
            )

        if order.get("ref_id") == request.ref_id:
            broker_order_id = order.get("id")

            if (
                not isinstance(broker_order_id, str)
                or not broker_order_id.strip()
            ):
                raise ValueError(
                    "matched Robinhood order must contain id"
                )

            return RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.FOUND,
                broker_order_id=broker_order_id,
            )

    return RobinhoodOrderLookupResult(
        status=RobinhoodOrderLookupStatus.UNKNOWN,
        message=(
            "Robinhood order history contains candidate "
            "orders but does not provide an exact ref_id match"
        ),
    )


class MCPRobinhoodOrderLookup:
    def __init__(
        self,
        invoker: MCPToolInvoker,
    ) -> None:
        self._invoker = invoker

    def lookup(
        self,
        request: PlacementReconciliationRequest,
    ) -> RobinhoodOrderLookupResult:
        call = build_robinhood_mcp_order_lookup_call(
            request
        )

        raw_result = self._invoker.call_tool(
            call.tool_name,
            call.arguments,
        )

        return decode_robinhood_mcp_order_lookup(
            request,
            raw_result,
        )