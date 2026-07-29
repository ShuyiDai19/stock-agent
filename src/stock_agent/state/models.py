from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from stock_agent.domain import AssetType


class PositionStateStatus(StrEnum):
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_positive(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PositionRuntimeState:
    position_id: str
    account_number: str
    asset_type: AssetType
    symbol: str
    opening_order_id: str
    entry_price: Decimal
    remaining_quantity: Decimal
    opened_at: datetime

    highest_executable_bid: Decimal
    trailing_armed: bool
    trailing_armed_at: datetime | None
    activation_gain_ratio: Decimal
    drawdown_ratio: Decimal

    last_quote_at: datetime
    last_reconciled_at: datetime
    status: PositionStateStatus = PositionStateStatus.ACTIVE

    option_id: str | None = None
    historical_high_unknown: bool = False
    version: int = 1

    def __post_init__(self) -> None:
        _require_non_empty(self.position_id, "position_id")
        _require_non_empty(self.account_number, "account_number")
        _require_non_empty(self.opening_order_id, "opening_order_id")

        symbol = self.symbol.strip().upper()
        _require_non_empty(symbol, "symbol")
        object.__setattr__(self, "symbol", symbol)

        _require_positive(self.entry_price, "entry_price")
        _require_non_negative(
            self.remaining_quantity,
            "remaining_quantity",
        )
        _require_non_negative(
            self.highest_executable_bid,
            "highest_executable_bid",
        )
        _require_positive(
            self.activation_gain_ratio,
            "activation_gain_ratio",
        )
        _require_positive(
            self.drawdown_ratio,
            "drawdown_ratio",
        )

        _require_timezone_aware(self.opened_at, "opened_at")
        _require_timezone_aware(self.last_quote_at, "last_quote_at")
        _require_timezone_aware(
            self.last_reconciled_at,
            "last_reconciled_at",
        )

        if self.trailing_armed_at is not None:
            _require_timezone_aware(
                self.trailing_armed_at,
                "trailing_armed_at",
            )

        if self.trailing_armed and self.trailing_armed_at is None:
            raise ValueError(
                "trailing_armed_at is required when trailing is armed"
            )

        if not self.trailing_armed and self.trailing_armed_at is not None:
            raise ValueError(
                "trailing_armed_at must be empty when trailing is not armed"
            )

        if self.asset_type is AssetType.OPTION and not self.option_id:
            raise ValueError(
                "option_id is required for option position state"
            )

        if self.asset_type is AssetType.EQUITY and self.option_id is not None:
            raise ValueError(
                "option_id is not allowed for equity position state"
            )

        if self.version < 1:
            raise ValueError("version must be at least 1")

        if (
            self.status is PositionStateStatus.CLOSED
            and self.remaining_quantity != Decimal("0")
        ):
            raise ValueError(
                "closed position state must have zero remaining quantity"
            )
