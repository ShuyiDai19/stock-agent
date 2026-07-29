from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from stock_agent.domain.enums import (
    AccountType,
    AssetType,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionEffect,
    TimeInForce,
)


def _require_non_negative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def _require_positive(value: Decimal, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class TradeIntent:
    symbol: str
    asset_type: AssetType
    side: OrderSide
    position_effect: PositionEffect
    notional: Decimal | None = None
    quantity: Decimal | None = None
    option_id: str | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol cannot be empty")

        object.__setattr__(self, "symbol", symbol)

        if (self.notional is None) == (self.quantity is None):
            raise ValueError("exactly one of notional or quantity must be provided")

        if self.notional is not None:
            _require_positive(self.notional, "notional")

        if self.quantity is not None:
            _require_positive(self.quantity, "quantity")

        if self.asset_type is AssetType.OPTION and not self.option_id:
            raise ValueError("option_id is required for option intents")

        if self.asset_type is AssetType.EQUITY and self.option_id is not None:
            raise ValueError("option_id is not allowed for equity intents")


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account_number: str
    account_type: AccountType
    agentic_allowed: bool
    portfolio_value: Decimal
    cash: Decimal
    buying_power: Decimal
    captured_at: datetime

    def __post_init__(self) -> None:
        if not self.account_number.strip():
            raise ValueError("account_number cannot be empty")

        _require_non_negative(self.portfolio_value, "portfolio_value")
        _require_non_negative(self.cash, "cash")
        _require_non_negative(self.buying_power, "buying_power")
        _require_timezone_aware(self.captured_at, "captured_at")

    @property
    def masked_account_number(self) -> str:
        suffix = self.account_number[-4:]
        return f"••••{suffix}"


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    asset_type: AssetType
    quantity: Decimal
    average_price: Decimal
    current_bid: Decimal
    option_id: str | None = None
    expiration_date: date | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol cannot be empty")

        object.__setattr__(self, "symbol", symbol)

        _require_positive(self.quantity, "quantity")
        _require_non_negative(self.average_price, "average_price")
        _require_non_negative(self.current_bid, "current_bid")

        if self.asset_type is AssetType.OPTION and not self.option_id:
            raise ValueError("option_id is required for option positions")

        if self.asset_type is AssetType.EQUITY:
            if self.option_id is not None:
                raise ValueError("option_id is not allowed for equity positions")
            if self.expiration_date is not None:
                raise ValueError("expiration_date is not allowed for equity positions")


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    order_id: str
    symbol: str
    asset_type: AssetType
    side: OrderSide
    position_effect: PositionEffect
    order_type: OrderType
    time_in_force: TimeInForce
    status: OrderStatus
    quantity: Decimal | None
    notional: Decimal | None
    limit_price: Decimal | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("order_id cannot be empty")

        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol cannot be empty")

        object.__setattr__(self, "symbol", symbol)
        _require_timezone_aware(self.created_at, "created_at")

        if self.quantity is not None:
            _require_positive(self.quantity, "quantity")

        if self.notional is not None:
            _require_positive(self.notional, "notional")

        if self.limit_price is not None:
            _require_positive(self.limit_price, "limit_price")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    current_price: Decimal
    bid: Decimal
    ask: Decimal
    session_open: Decimal
    captured_at: datetime
    ma20: Decimal | None = None
    ma50: Decimal | None = None
    rsi14: Decimal | None = None
    vwap: Decimal | None = None
    recent_five_minute_closes: tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol cannot be empty")

        object.__setattr__(self, "symbol", symbol)

        _require_positive(self.current_price, "current_price")
        _require_non_negative(self.bid, "bid")
        _require_non_negative(self.ask, "ask")
        _require_positive(self.session_open, "session_open")
        _require_timezone_aware(self.captured_at, "captured_at")

        if self.ask and self.bid and self.ask < self.bid:
            raise ValueError("ask cannot be below bid")

    @property
    def midpoint(self) -> Decimal | None:
        if self.bid <= 0 or self.ask <= 0:
            return None

        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread_ratio(self) -> Decimal | None:
        midpoint = self.midpoint
        if midpoint is None or midpoint <= 0:
            return None

        return (self.ask - self.bid) / midpoint
