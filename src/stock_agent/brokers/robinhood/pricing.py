from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)
from stock_agent.domain import AssetType

from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)


@dataclass(frozen=True)
class RobinhoodExitPriceQuote:
    symbol: str
    executable_bid: Decimal
    observed_at: datetime
    option_id: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if not self.executable_bid.is_finite():
            raise ValueError(
                "executable_bid must be finite"
            )

        if self.executable_bid <= 0:
            raise ValueError(
                "executable_bid must be greater than zero"
            )

        if (
            self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise ValueError(
                "observed_at must be timezone-aware"
            )

        if (
            self.option_id is not None
            and not self.option_id.strip()
        ):
            raise ValueError(
                "option_id cannot be empty"
            )


class RobinhoodExitPriceProvider(Protocol):
    def get_exit_price(
        self,
        request: RobinhoodExitOrderRequest,
    ) -> RobinhoodExitPriceQuote:
        ...


    def build_robinhood_exit_submission(
        request: RobinhoodExitOrderRequest,
        quote: RobinhoodExitPriceQuote,
    ) -> RobinhoodExitSubmission:
        if quote.symbol != request.symbol:
            raise ValueError(
                "exit price quote symbol does not match request symbol"
            )

        if quote.option_id != request.option_id:
            raise ValueError(
                "exit price quote option_id does not match request option_id"
            )

        if request.asset_type is AssetType.EQUITY:
            return RobinhoodExitSubmission(
                request=request,
                order_type=RobinhoodOrderType.MARKET,
                limit_price=None,
            )

        if request.asset_type is AssetType.OPTION:
            return RobinhoodExitSubmission(
                request=request,
                order_type=RobinhoodOrderType.LIMIT,
                limit_price=quote.executable_bid,
            )

        raise ValueError(
            f"unsupported asset type: {request.asset_type}"
        )