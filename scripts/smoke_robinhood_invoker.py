import os

from stock_agent.brokers.robinhood.connection import (
    open_robinhood_mcp_invoker,
)


def main() -> None:
    account_number = os.environ.get(
        "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER"
    )

    if not account_number:
        raise RuntimeError(
            "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER "
            "is not set"
        )

    with open_robinhood_mcp_invoker(
        allowed_account_number=account_number,
        startup_timeout_seconds=300.0,
    ) as invoker:
        result = invoker.call_tool(
            "get_equity_orders",
            {
                "account_number": account_number,
                "placed_agent": "agentic",
            },
        )

        data = result.get("data")

        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "missing data object"
            )

        orders = data.get("orders")

        if not isinstance(
            orders,
            list,
        ):
            raise RuntimeError(
                "missing orders list"
            )

        print(
            "\nPersistent MCP invoker connected "
            "successfully."
        )

        print(
            "Order count:",
            len(orders),
        )

        for order in orders[:5]:
            print(
                {
                    "symbol": order.get(
                        "symbol"
                    ),
                    "side": order.get(
                        "side"
                    ),
                    "state": order.get(
                        "state"
                    ),
                    "created_at": order.get(
                        "created_at"
                    ),
                }
            )


if __name__ == "__main__":
    main()