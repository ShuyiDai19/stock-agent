from typing import Protocol

from stock_agent.domain import QuoteSnapshot


class QuoteProvider(Protocol):
    def get_quote(
        self,
        symbol: str,
    ) -> QuoteSnapshot:
        ...