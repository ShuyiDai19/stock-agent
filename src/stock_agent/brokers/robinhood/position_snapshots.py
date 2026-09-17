from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class RobinhoodEquityPositionType(
    str,
    Enum,
):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class RobinhoodEquityPositionSnapshot:
    symbol: str
    quantity: Decimal
    intraday_quantity: Decimal
    average_buy_price: Decimal | None
    shares_available_for_sells: Decimal
    position_type: RobinhoodEquityPositionType

    def __post_init__(
        self,
    ) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol must not be empty"
            )

        if self.quantity < 0:
            raise ValueError(
                "quantity cannot be negative"
            )

        if self.intraday_quantity < 0:
            raise ValueError(
                "intraday_quantity cannot "
                "be negative"
            )

        if (
            self.average_buy_price is not None
            and self.average_buy_price < 0
        ):
            raise ValueError(
                "average_buy_price cannot "
                "be negative"
            )

        if self.shares_available_for_sells < 0:
            raise ValueError(
                "shares_available_for_sells "
                "cannot be negative"
            )

        if (
            self.shares_available_for_sells
            > self.quantity
        ):
            raise ValueError(
                "shares_available_for_sells "
                "cannot exceed quantity"
            )