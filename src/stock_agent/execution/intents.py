from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from stock_agent.domain import AssetType


class ExitReason(str, Enum):
    TRAILING_STOP = "trailing_stop"


@dataclass(frozen=True)
class ExitIntent:
    position_id: str
    account_number: str
    asset_type: AssetType
    symbol: str
    quantity: Decimal
    reason: ExitReason
    triggered_at: datetime
    option_id: str | None = None

    def __post_init__(self) -> None:
        if not self.position_id.strip():
            raise ValueError("position_id cannot be empty")

        if not self.account_number.strip():
            raise ValueError("account_number cannot be empty")

        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")

        if not self.quantity.is_finite():
            raise ValueError("quantity must be finite")

        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")

        if (
            self.triggered_at.tzinfo is None
            or self.triggered_at.utcoffset() is None
        ):
            raise ValueError("triggered_at must be timezone-aware")