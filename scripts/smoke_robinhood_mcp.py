from stock_agent.brokers.robinhood.persistent_mcp_invoker import (
    PersistentMCPToolInvoker,
)


ROBINHOOD_MCP_URL = (
    "https://agent.robinhood.com/mcp/trading"
)


def main() -> None:
    with PersistentMCPToolInvoker(
        ROBINHOOD_MCP_URL,
    ) as invoker:
        result = invoker.list_tools()

        print(result)


if __name__ == "__main__":
    main()