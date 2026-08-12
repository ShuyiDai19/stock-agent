from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    bid: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")

        if not self.bid.is_finite():
            raise ValueError("bid must be finite")

        if self.bid <= 0:
            raise ValueError("bid must be greater than zero")

        if (
            self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be timezone-aware")