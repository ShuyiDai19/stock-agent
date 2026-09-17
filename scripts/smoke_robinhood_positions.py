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
        equity_result = invoker.call_tool(
            "get_equity_positions",
            {
                "account_number":
                    account_number,
            },
        )

        option_result = invoker.call_tool(
            "get_option_positions",
            {
                "account_number":
                    account_number,
                "nonzero": True,
            },
        )

        print(
            "Equity positions:"
        )
        print(
            equity_result
        )

        print()
        print(
            "Open option positions:"
        )
        print(
            option_result
        )

    print(
        "Equity top-level keys:",
        list(equity_result.keys()),
    )

    equity_data = equity_result.get(
        "data"
    )

    if isinstance(
        equity_data,
        dict,
    ):
        print(
            "Equity data keys:",
            list(equity_data.keys()),
        )

    print(
        "Equity top-level next:",
        equity_result.get(
            "next",
            "<missing>",
        ),
    )

    if isinstance(
        equity_data,
        dict,
    ):
        print(
            "Equity data next:",
            equity_data.get(
                "next",
                "<missing>",
            ),
        )

    print(
        "Option top-level keys:",
        list(option_result.keys()),
    )

    option_data = option_result.get(
        "data"
    )

    if isinstance(
        option_data,
        dict,
    ):
        print(
            "Option data keys:",
            list(option_data.keys()),
        )

    print(
        "Option top-level next:",
        option_result.get(
            "next",
            "<missing>",
        ),
    )

    if isinstance(
        option_data,
        dict,
    ):
        print(
            "Option data next:",
            option_data.get(
                "next",
                "<missing>",
            ),
        )


if __name__ == "__main__":
    main()