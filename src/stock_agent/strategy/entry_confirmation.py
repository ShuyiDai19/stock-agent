from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class EntryConfirmationReason(StrEnum):
    PRICE_NOT_ABOVE_OPEN = (
        "price_not_above_open"
    )
    PRICE_NOT_ABOVE_VWAP = (
        "price_not_above_vwap"
    )
    TWO_CONSECUTIVE_LOWER_CLOSES = (
        "two_consecutive_lower_closes"
    )


@dataclass(frozen=True, slots=True)
class BullishEntrySnapshot:
    symbol: str
    price: Decimal
    session_open: Decimal
    vwap: Decimal
    recent_5m_closes: tuple[
        Decimal,
        Decimal,
        Decimal,
    ]
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if self.symbol != self.symbol.upper():
            raise ValueError(
                "symbol must be uppercase"
            )

        for field_name, value in (
            ("price", self.price),
            ("session_open", self.session_open),
            ("vwap", self.vwap),
        ):
            if not value.is_finite():
                raise ValueError(
                    f"{field_name} must be finite"
                )

            if value <= 0:
                raise ValueError(
                    f"{field_name} must be "
                    "greater than zero"
                )

        if len(self.recent_5m_closes) != 3:
            raise ValueError(
                "recent_5m_closes must contain "
                "exactly three closes"
            )

        for close in self.recent_5m_closes:
            if not close.is_finite():
                raise ValueError(
                    "5-minute close must be finite"
                )

            if close <= 0:
                raise ValueError(
                    "5-minute close must be "
                    "greater than zero"
                )

        if (
            self.observed_at.tzinfo is None
            or self.observed_at.utcoffset()
            is None
        ):
            raise ValueError(
                "observed_at must be timezone-aware"
            )


@dataclass(frozen=True, slots=True)
class EntryConfirmationDecision:
    reasons: frozenset[
        EntryConfirmationReason
    ]

    @property
    def approved(self) -> bool:
        return not self.reasons


def evaluate_bullish_entry_confirmation(
    snapshot: BullishEntrySnapshot,
) -> EntryConfirmationDecision:
    reasons: set[
        EntryConfirmationReason
    ] = set()

    if (
        snapshot.price
        <= snapshot.session_open
    ):
        reasons.add(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_OPEN
        )

    if snapshot.price <= snapshot.vwap:
        reasons.add(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_VWAP
        )

    first, second, third = (
        snapshot.recent_5m_closes
    )

    if (
        second < first
        and third < second
    ):
        reasons.add(
            EntryConfirmationReason
            .TWO_CONSECUTIVE_LOWER_CLOSES
        )

    return EntryConfirmationDecision(
        reasons=frozenset(
            reasons
        )
    )