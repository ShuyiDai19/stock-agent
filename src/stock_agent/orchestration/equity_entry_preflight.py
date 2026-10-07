from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo
from decimal import Decimal


_NEW_YORK = ZoneInfo(
    "America/New_York"
)


class EquityEntryPreflightBlocker(
    StrEnum
):
    OUTSIDE_ENTRY_WINDOW = (
        "outside_entry_window"
    )
    EXISTING_POSITION = (
        "existing_position"
    )
    OPEN_EQUITY_ORDER = (
        "open_equity_order"
    )
    OPEN_OPTION_ORDER = (
        "open_option_order"
    )
    OPENING_ORDER_ALREADY_SUBMITTED_TODAY = (
        "opening_order_already_submitted_today"
    )
    INSUFFICIENT_BUYING_POWER = (
        "insufficient_buying_power"
    )
    INSUFFICIENT_CASH_RESERVE = (
        "insufficient_cash_reserve"
    )
    DATA_UNAVAILABLE = (
        "data_unavailable"
    )

class EquityEntryPreflightDataSource(
    StrEnum
):
    POSITIONS = "positions"
    OPTION_EXPOSURE = "option_exposure"
    ORDER_ACTIVITY = "order_activity"
    FUNDS = "funds"


class EquityEntryPreflightDataUnavailableError(
    RuntimeError
):
    def __init__(
        self,
        source: EquityEntryPreflightDataSource,
        cause: Exception,
    ) -> None:
        self.source = source
        self.cause = cause

        super().__init__(
            "equity entry preflight data "
            f"unavailable: {source.value}"
        )


@dataclass(
    frozen=True,
    slots=True,
)
class EquityEntryPreflightSnapshot:
    has_existing_position: bool
    has_open_equity_order: bool
    has_open_option_order: bool
    has_opening_order_today: bool

    buying_power: Decimal
    cash: Decimal

    def __post_init__(self) -> None:
        if self.buying_power < Decimal("0"):
            raise ValueError(
                "buying_power cannot be negative"
            )

        if self.cash < Decimal("0"):
            raise ValueError(
                "cash cannot be negative"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class EquityEntryPreflightResult:
    blockers: tuple[
        EquityEntryPreflightBlocker,
        ...
    ]

    unavailable_sources: tuple[
        EquityEntryPreflightDataSource,
        ...
    ] = ()

    @property
    def eligible(self) -> bool:
        return not self.blockers

def evaluate_equity_entry_preflight(
    snapshot: EquityEntryPreflightSnapshot,
    *,
    evaluated_at: datetime,
    opening_debit: Decimal,
    minimum_cash_reserve: Decimal = (
        Decimal("5")
    ),
) -> EquityEntryPreflightResult:
    if (
        opening_debit <= Decimal("0")
    ):
        raise ValueError(
            "opening_debit must be positive"
        )

    if (
        minimum_cash_reserve
        < Decimal("0")
    ):
        raise ValueError(
            "minimum_cash_reserve "
            "cannot be negative"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset()
        is None
    ):
        raise ValueError(
            "evaluated_at must be "
            "timezone-aware"
        )

    local_time = (
        evaluated_at
        .astimezone(_NEW_YORK)
    )

    blockers = []

    if (
        local_time.weekday() >= 5
        or not (
            (
                local_time.hour,
                local_time.minute,
            )
            >= (10, 15)
            and (
                local_time.hour,
                local_time.minute,
            )
            <= (15, 30)
        )
    ):
        blockers.append(
            EquityEntryPreflightBlocker
            .OUTSIDE_ENTRY_WINDOW
        )

    if snapshot.has_existing_position:
        blockers.append(
            EquityEntryPreflightBlocker
            .EXISTING_POSITION
        )

    if snapshot.has_open_equity_order:
        blockers.append(
            EquityEntryPreflightBlocker
            .OPEN_EQUITY_ORDER
        )

    if snapshot.has_open_option_order:
        blockers.append(
            EquityEntryPreflightBlocker
            .OPEN_OPTION_ORDER
        )

    if snapshot.has_opening_order_today:
        blockers.append(
            EquityEntryPreflightBlocker
            .OPENING_ORDER_ALREADY_SUBMITTED_TODAY
        )

    if (
        snapshot.buying_power
        < opening_debit
    ):
        blockers.append(
            EquityEntryPreflightBlocker
            .INSUFFICIENT_BUYING_POWER
        )

    remaining_cash = (
        snapshot.cash
        - opening_debit
    )

    if (
        remaining_cash
        < minimum_cash_reserve
    ):
        blockers.append(
            EquityEntryPreflightBlocker
            .INSUFFICIENT_CASH_RESERVE
        )


    return EquityEntryPreflightResult(
        blockers=tuple(blockers)
    )