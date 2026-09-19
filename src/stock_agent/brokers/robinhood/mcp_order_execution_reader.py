from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.brokers.robinhood.order_execution_decoder import (
    decode_robinhood_filled_order,
)


class MCPRobinhoodEquityOrderExecutionReader:
    def __init__(
        self,
        invoker: MCPToolInvoker,
    ) -> None:
        self._invoker = invoker

    def read(
        self,
        *,
        account_number: str,
        broker_order_id: str,
        ref_id: str,
    ) -> RobinhoodOrderExecutionSnapshot | None:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if not broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if not ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        raw_result = self._invoker.call_tool(
            "get_equity_orders",
            {
                "account_number": account_number,
                "order_id": broker_order_id,
            },
        )

        order = _extract_single_order(
            raw_result
        )

        if order is None:
            return None

        return decode_robinhood_filled_order(
            order,
            expected_broker_order_id=(
                broker_order_id
            ),
            expected_ref_id=ref_id,
        )


def _extract_single_order(
    raw_result: Any,
) -> dict[str, Any] | None:
    if not isinstance(raw_result, dict):
        raise ValueError(
            "Robinhood order execution result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(data, dict):
        raise ValueError(
            "Robinhood order execution result "
            "must contain data"
        )

    orders = data.get(
        "orders"
    )

    if not isinstance(orders, list):
        raise ValueError(
            "Robinhood order execution result "
            "must contain orders"
        )

    if not orders:
        return None

    if len(orders) != 1:
        raise ValueError(
            "Robinhood single-order lookup "
            "must return at most one order"
        )

    order = orders[0]

    if not isinstance(order, dict):
        raise ValueError(
            "Robinhood order must be a mapping"
        )

    return order