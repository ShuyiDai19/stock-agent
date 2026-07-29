from enum import StrEnum


class AssetType(StrEnum):
    EQUITY = "equity"
    OPTION = "option"


class AccountType(StrEnum):
    CASH = "cash"
    MARGIN = "margin"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class PositionEffect(StrEnum):
    OPEN = "open"
    CLOSE = "close"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    GOOD_FOR_DAY = "gfd"
    GOOD_TILL_CANCELLED = "gtc"


class OrderStatus(StrEnum):
    NEW = "new"
    QUEUED = "queued"
    CONFIRMED = "confirmed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"
