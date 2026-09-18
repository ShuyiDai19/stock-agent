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
            "must be set"
        )

    with open_robinhood_mcp_invoker(
        allowed_account_number=account_number,
        startup_timeout_seconds=300.0,
    ) as invoker:
        result = invoker.call_tool(
            "get_equity_quotes",
            {
                "symbols": [
                    "AAPL",
                ],
            },
        )

        print(
            "Top-level keys:",
            list(result.keys()),
        )

        data = result.get("data")

        if isinstance(data, dict):
            print(
                "Data keys:",
                list(data.keys()),
            )

        print(
            "Quote result:"
        )
        print(
            result
        )


if __name__ == "__main__":
    main()