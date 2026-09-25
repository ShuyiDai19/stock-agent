from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.pricing import (
    RobinhoodExitPriceQuote,
)
from stock_agent.domain import AssetType
from stock_agent.market_data import QuoteProvider


class RobinhoodEquityExitPriceProvider:
    def __init__(
        self,
        quote_provider: QuoteProvider,
    ) -> None:
        self._quote_provider = (
            quote_provider
        )

    def get_exit_price(
        self,
        request: RobinhoodExitOrderRequest,
    ) -> RobinhoodExitPriceQuote:
        if (
            request.asset_type
            is not AssetType.EQUITY
        ):
            raise ValueError(
                "equity exit price provider "
                "requires an equity request"
            )

        if request.option_id is not None:
            raise ValueError(
                "equity exit price request "
                "cannot contain option_id"
            )

        quote = (
            self._quote_provider
            .get_quote(
                request.symbol
            )
        )

        if (
            quote.symbol
            != request.symbol
        ):
            raise ValueError(
                "quote symbol does not match "
                "exit request symbol"
            )

        return RobinhoodExitPriceQuote(
            symbol=request.symbol,
            executable_bid=quote.bid,
            observed_at=(
                quote.observed_at
            ),
            option_id=None,
        )