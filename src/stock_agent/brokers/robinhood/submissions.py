from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitOrderRequest,
)


class RobinhoodOrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class RobinhoodTimeInForce(str, Enum):
    GFD = "gfd"


class RobinhoodMarketHours(str, Enum):
    REGULAR_HOURS = "regular_hours"


@dataclass(frozen=True)
class RobinhoodExitSubmission:
    request: RobinhoodExitOrderRequest
    order_type: RobinhoodOrderType
    time_in_force: RobinhoodTimeInForce = RobinhoodTimeInForce.GFD
    market_hours: RobinhoodMarketHours = (
        RobinhoodMarketHours.REGULAR_HOURS
    )
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.order_type is RobinhoodOrderType.LIMIT:
            if self.limit_price is None:
                raise ValueError(
                    "limit order requires limit_price"
                )

            if not self.limit_price.is_finite():
                raise ValueError(
                    "limit_price must be finite"
                )

            if self.limit_price <= 0:
                raise ValueError(
                    "limit_price must be greater than zero"
                )

        if (
            self.order_type is RobinhoodOrderType.MARKET
            and self.limit_price is not None
        ):
            raise ValueError(
                "market order cannot contain limit_price"
            )