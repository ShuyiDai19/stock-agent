from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.domain import (
    AssetType,
    QuoteSnapshot,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStore,
    PositionStateStatus,
)


DEFAULT_TRAILING_ACTIVATION_GAIN = Decimal(
    "0.04"
)

DEFAULT_TRAILING_DRAWDOWN = Decimal(
    "0.02"
)


class EntryPositionActivationError(
    RuntimeError
):
    pass


@dataclass(frozen=True, slots=True)
class ConfirmedEquityEntryFill:
    account_number: str
    symbol: str
    broker_order_id: str
    ref_id: str
    filled_quantity: Decimal
    average_fill_price: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        if not self.account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if self.symbol != self.symbol.upper():
            raise ValueError(
                "symbol must be uppercase"
            )

        if not self.broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if not self.ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        for field_name, value in (
            (
                "filled_quantity",
                self.filled_quantity,
            ),
            (
                "average_fill_price",
                self.average_fill_price,
            ),
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

        if (
            self.filled_at.tzinfo is None
            or self.filled_at.utcoffset()
            is None
        ):
            raise ValueError(
                "filled_at must be timezone-aware"
            )


def build_active_equity_position(
    fill: ConfirmedEquityEntryFill,
    *,
    initial_quote: QuoteSnapshot,
    activation_gain_ratio: Decimal = (
        DEFAULT_TRAILING_ACTIVATION_GAIN
    ),
    drawdown_ratio: Decimal = (
        DEFAULT_TRAILING_DRAWDOWN
    ),
) -> PositionRuntimeState:
    if initial_quote.symbol != fill.symbol:
        raise EntryPositionActivationError(
            "initial quote symbol must match fill symbol"
        )

    if (
        initial_quote.observed_at
        < fill.filled_at
    ):
        raise EntryPositionActivationError(
            "initial quote must not predate fill"
        )

    position_id = (
        f"{fill.account_number}:"
        f"equity:"
        f"{fill.symbol}:"
        f"{fill.broker_order_id}"
    )

    return PositionRuntimeState(
        position_id=position_id,
        account_number=fill.account_number,
        asset_type=AssetType.EQUITY,
        symbol=fill.symbol,
        opening_order_id=(
            fill.broker_order_id
        ),
        entry_price=(
            fill.average_fill_price
        ),
        remaining_quantity=(
            fill.filled_quantity
        ),
        opened_at=fill.filled_at,
        highest_executable_bid=(
            initial_quote.bid
        ),
        trailing_armed=False,
        trailing_armed_at=None,
        activation_gain_ratio=(
            activation_gain_ratio
        ),
        drawdown_ratio=(
            drawdown_ratio
        ),
        last_quote_at=(
            initial_quote.observed_at
        ),
        last_reconciled_at=(
            fill.filled_at
        ),
        status=PositionStateStatus.ACTIVE,
        option_id=None,
        historical_high_unknown=False,
        version=1,
    )


def activate_filled_equity_entry(
    store: PositionStateStore,
    fill: ConfirmedEquityEntryFill,
    *,
    initial_quote: QuoteSnapshot,
) -> PositionRuntimeState:
    state = build_active_equity_position(
        fill,
        initial_quote=initial_quote,
    )

    existing = store.get(
        state.position_id
    )

    if existing is not None:
        if (
            existing.account_number
            == state.account_number
            and existing.asset_type
            is AssetType.EQUITY
            and existing.symbol
            == state.symbol
            and existing.opening_order_id
            == state.opening_order_id
        ):
            return existing

        raise EntryPositionActivationError(
            "position id already exists "
            "with different provenance"
        )

    store.insert(
        state
    )

    return state