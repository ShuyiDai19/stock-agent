from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_quote_decoder import (
    decode_robinhood_equity_quote,
)
from stock_agent.domain import QuoteSnapshot


class MCPRobinhoodEquityQuoteProvider:
    def __init__(
        self,
        invoker: MCPToolInvoker,
    ) -> None:
        self._invoker = invoker

    def get_quote(
        self,
        symbol: str,
    ) -> QuoteSnapshot:
        normalized_symbol = (
            symbol.strip().upper()
        )

        if not normalized_symbol:
            raise ValueError(
                "symbol cannot be empty"
            )

        payload = self._invoker.call_tool(
            "get_equity_quotes",
            {
                "symbols": [
                    normalized_symbol,
                ],
            },
        )

        return decode_robinhood_equity_quote(
            payload,
            expected_symbol=normalized_symbol,
        )