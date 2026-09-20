from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class EquityUniverseRejectReason(
    StrEnum
):
    BELOW_MIN_AVERAGE_VOLUME = (
        "below_min_average_volume"
    )

    BELOW_MIN_MARKET_CAP = (
        "below_min_market_cap"
    )


@dataclass(frozen=True, slots=True)
class EquityUniverseScreeningPolicy:
    min_average_volume_30d: Decimal
    min_market_cap: Decimal

    def __post_init__(
        self,
    ) -> None:
        for field_name, value in (
            (
                "min_average_volume_30d",
                self.min_average_volume_30d,
            ),
            (
                "min_market_cap",
                self.min_market_cap,
            ),
        ):
            if not value.is_finite():
                raise ValueError(
                    f"{field_name} must be finite"
                )

            if value < 0:
                raise ValueError(
                    f"{field_name} cannot be negative"
                )


@dataclass(frozen=True, slots=True)
class EquityUniverseSnapshot:
    symbol: str
    average_volume_30d: Decimal
    market_cap: Decimal

    def __post_init__(
        self,
    ) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if self.symbol != self.symbol.upper():
            raise ValueError(
                "symbol must be uppercase"
            )

        for field_name, value in (
            (
                "average_volume_30d",
                self.average_volume_30d,
            ),
            (
                "market_cap",
                self.market_cap,
            ),
        ):
            if not value.is_finite():
                raise ValueError(
                    f"{field_name} must be finite"
                )

            if value < 0:
                raise ValueError(
                    f"{field_name} cannot be negative"
                )


@dataclass(frozen=True, slots=True)
class EquityUniverseScreenItem:
    snapshot: EquityUniverseSnapshot

    reasons: frozenset[
        EquityUniverseRejectReason
    ]

    @property
    def symbol(
        self,
    ) -> str:
        return self.snapshot.symbol

    @property
    def eligible(
        self,
    ) -> bool:
        return not self.reasons


@dataclass(frozen=True, slots=True)
class EquityUniverseScreenOutcome:
    items: tuple[
        EquityUniverseScreenItem,
        ...,
    ]

    @property
    def eligible_items(
        self,
    ) -> tuple[
        EquityUniverseScreenItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if item.eligible
        )

    @property
    def rejected_items(
        self,
    ) -> tuple[
        EquityUniverseScreenItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if not item.eligible
        )

    @property
    def eligible_symbols(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        return tuple(
            item.symbol
            for item in self.eligible_items
        )


def screen_equity_universe(
    snapshots: tuple[
        EquityUniverseSnapshot,
        ...,
    ],
    *,
    policy: EquityUniverseScreeningPolicy,
) -> EquityUniverseScreenOutcome:
    seen_symbols = set()
    items = []

    for snapshot in snapshots:
        if snapshot.symbol in seen_symbols:
            raise ValueError(
                "universe snapshots cannot "
                "contain duplicate symbols"
            )

        seen_symbols.add(
            snapshot.symbol
        )

        reasons = set()

        if (
            snapshot.average_volume_30d
            < policy.min_average_volume_30d
        ):
            reasons.add(
                EquityUniverseRejectReason
                .BELOW_MIN_AVERAGE_VOLUME
            )

        if (
            snapshot.market_cap
            < policy.min_market_cap
        ):
            reasons.add(
                EquityUniverseRejectReason
                .BELOW_MIN_MARKET_CAP
            )

        items.append(
            EquityUniverseScreenItem(
                snapshot=snapshot,
                reasons=frozenset(
                    reasons
                ),
            )
        )

    return EquityUniverseScreenOutcome(
        items=tuple(
            items
        )
    )