from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitOrderRequest,
)


class RobinhoodOrderType(str, Enum):
    LIMIT = "limit"


class RobinhoodTimeInForce(str, Enum):
    GFD = "gfd"


@dataclass(frozen=True)
class RobinhoodExitSubmission:
    request: RobinhoodExitOrderRequest
    limit_price: Decimal
    order_type: RobinhoodOrderType = RobinhoodOrderType.LIMIT
    time_in_force: RobinhoodTimeInForce = RobinhoodTimeInForce.GFD

    def __post_init__(self) -> None:
        if not self.limit_price.is_finite():
            raise ValueError(
                "limit_price must be finite"
            )

        if self.limit_price <= 0:
            raise ValueError(
                "limit_price must be greater than zero"
            )