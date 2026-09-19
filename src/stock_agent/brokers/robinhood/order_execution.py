from dataclasses import dataclass
from decimal import Decimal

from stock_agent.domain.enums import (
    OrderStatus,
)


@dataclass(frozen=True, slots=True)
class RobinhoodOrderExecutionSnapshot:
    broker_order_id: str
    ref_id: str
    status: OrderStatus
    quantity: Decimal
    filled_quantity: Decimal

    def __post_init__(
        self,
    ) -> None:
        if not self.broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if not self.ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        if not self.quantity.is_finite():
            raise ValueError(
                "quantity must be finite"
            )

        if self.quantity <= 0:
            raise ValueError(
                "quantity must be greater than zero"
            )

        if not self.filled_quantity.is_finite():
            raise ValueError(
                "filled_quantity must be finite"
            )

        if self.filled_quantity < 0:
            raise ValueError(
                "filled_quantity cannot be negative"
            )

        if self.filled_quantity > self.quantity:
            raise ValueError(
                "filled_quantity cannot exceed quantity"
            )

        if (
            self.status
            is OrderStatus.FILLED
            and self.filled_quantity
            != self.quantity
        ):
            raise ValueError(
                "filled order must have "
                "filled_quantity equal to quantity"
            )

        if (
            self.status
            is OrderStatus.PARTIALLY_FILLED
            and not (
                Decimal("0")
                < self.filled_quantity
                < self.quantity
            )
        ):
            raise ValueError(
                "partially filled order must have "
                "filled_quantity between zero "
                "and quantity"
            )

    @property
    def remaining_quantity(
        self,
    ) -> Decimal:
        return (
            self.quantity
            - self.filled_quantity
        )

    @property
    def confirms_full_fill(
        self,
    ) -> bool:
        return (
            self.status
            is OrderStatus.FILLED
            and self.filled_quantity
            == self.quantity
        )