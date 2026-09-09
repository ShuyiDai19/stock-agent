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
from urllib.parse import parse_qs, urlsplit


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

def _extract_next_cursor(
    raw_result: dict[str, Any],
) -> str | None:
    data = raw_result["data"]

    markers = [
        envelope["next"]
        for envelope in (raw_result, data)
        if "next" in envelope
    ]

    if not markers:
        raise ValueError(
            "Robinhood order lookup pagination metadata is missing"
        )

    if any(marker != markers[0] for marker in markers[1:]):
        raise ValueError(
            "Robinhood order lookup pagination metadata conflicts"
        )

    next_value = markers[0]

    if next_value is None:
        return None

    if not isinstance(next_value, str) or not next_value.strip():
        raise ValueError(
            "Robinhood order lookup next must be a nonempty URL"
        )

    parsed = urlsplit(next_value)

    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(
            "Robinhood order lookup next must be an HTTPS URL"
        )

    cursors = parse_qs(
        parsed.query,
        keep_blank_values=True,
    ).get("cursor", [])

    if len(cursors) != 1 or not cursors[0]:
        raise ValueError(
            "Robinhood order lookup next must contain one cursor"
        )

    return cursors[0]

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

    next_cursor = _extract_next_cursor(raw_result)

    if next_cursor is not None:
        return RobinhoodOrderLookupResult(
            status=RobinhoodOrderLookupStatus.UNKNOWN,
            message=(
                "Robinhood order lookup has additional pages; "
                "exact ref_id has not been found"
            ),
        )

    if not orders:
        return RobinhoodOrderLookupResult(
            status=RobinhoodOrderLookupStatus.NOT_FOUND,
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
        *,
        max_pages: int = 10,
    ) -> None:
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError(
                "max_pages must be a positive integer"
            )

        self._invoker = invoker
        self._max_pages = max_pages

    def lookup(
        self,
        request: PlacementReconciliationRequest,
    ) -> RobinhoodOrderLookupResult:
        call = build_robinhood_mcp_order_lookup_call(
            request
        )

        arguments = dict(call.arguments)
        seen_cursors: set[str] = set()
        saw_unverified_candidates = False

        for _ in range(self._max_pages):
            # Do not catch transport errors here.
            raw_result = self._invoker.call_tool(
                call.tool_name,
                arguments,
            )

            try:
                result = decode_robinhood_mcp_order_lookup(
                    request,
                    raw_result,
                )

                if result.status is RobinhoodOrderLookupStatus.FOUND:
                    return result

                next_cursor = _extract_next_cursor(
                    raw_result
                )

                if raw_result["data"]["orders"]:
                    saw_unverified_candidates = True

            except (ValueError, TypeError) as exc:
                return RobinhoodOrderLookupResult(
                    status=RobinhoodOrderLookupStatus.UNKNOWN,
                    message=f"order lookup response is inconclusive: {exc}",
                )

            if next_cursor is None:
                if saw_unverified_candidates:
                    return RobinhoodOrderLookupResult(
                        status=RobinhoodOrderLookupStatus.UNKNOWN,
                        message=(
                            "complete order lookup contains "
                            "unverified candidate orders"
                        ),
                    )

                return RobinhoodOrderLookupResult(
                    status=RobinhoodOrderLookupStatus.NOT_FOUND,
                )

            if next_cursor in seen_cursors:
                return RobinhoodOrderLookupResult(
                    status=RobinhoodOrderLookupStatus.UNKNOWN,
                    message="order lookup pagination cursor repeated",
                )

            seen_cursors.add(next_cursor)

            arguments = {
                **call.arguments,
                "cursor": next_cursor,
            }

        return RobinhoodOrderLookupResult(
            status=RobinhoodOrderLookupStatus.UNKNOWN,
            message="order lookup reached maximum page limit",
        )