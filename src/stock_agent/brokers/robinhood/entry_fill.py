from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from stock_agent.brokers.robinhood.entry_activation import (
    ConfirmedEquityEntryFill,
    activate_filled_equity_entry,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.domain import QuoteSnapshot
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStore,
)
from stock_agent.brokers.robinhood.entry_placement import (
    EntryPlacementStatus,
    SQLiteEquityEntryPlacementJournal,
)


class EquityEntryQuoteProvider(Protocol):
    def get_quote(
        self,
        symbol: str,
    ) -> QuoteSnapshot:
        ...


def _parse_positive_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if value is None:
        raise ValueError(
            f"{field_name} is missing"
        )

    try:
        parsed = Decimal(
            str(value)
        )
    except InvalidOperation as exc:
        raise ValueError(
            f"{field_name} is invalid"
        ) from exc

    if not parsed.is_finite():
        raise ValueError(
            f"{field_name} must be finite"
        )

    if parsed <= 0:
        raise ValueError(
            f"{field_name} must be "
            "greater than zero"
        )

    return parsed


def _parse_order_timestamp(
    value: Any,
    *,
    field_name: str,
):
    from datetime import datetime

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{field_name} is missing"
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise ValueError(
            f"{field_name} is invalid"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be "
            "timezone-aware"
        )

    return parsed


def decode_confirmed_equity_entry_fill(
    raw_result: Any,
    *,
    account_number: str,
    symbol: str,
    broker_order_id: str,
    ref_id: str,
) -> ConfirmedEquityEntryFill | None:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood equity order result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood equity order result "
            "must contain data"
        )

    orders = data.get(
        "orders"
    )

    if not isinstance(
        orders,
        list,
    ):
        raise ValueError(
            "Robinhood equity order result "
            "must contain orders"
        )

    if not orders:
        return None

    if len(orders) != 1:
        raise ValueError(
            "order_id lookup must return "
            "at most one equity order"
        )

    order = orders[0]

    if not isinstance(
        order,
        dict,
    ):
        raise ValueError(
            "Robinhood equity order "
            "must be a mapping"
        )

    if (
        order.get("id")
        != broker_order_id
    ):
        raise ValueError(
            "Robinhood equity order id "
            "does not match expected order"
        )

    if (
        order.get("ref_id")
        != ref_id
    ):
        raise ValueError(
            "Robinhood equity order ref_id "
            "does not match expected placement"
        )

    if (
        order.get("symbol")
        != symbol
    ):
        raise ValueError(
            "Robinhood equity order symbol "
            "does not match expected symbol"
        )

    if order.get("side") != "buy":
        raise ValueError(
            "opening equity order must be buy"
        )

    if order.get("state") != "filled":
        return None

    filled_quantity = (
        _parse_positive_decimal(
            order.get(
                "cumulative_quantity"
            ),
            field_name=(
                "cumulative_quantity"
            ),
        )
    )

    average_fill_price = (
        _parse_positive_decimal(
            order.get(
                "average_price"
            ),
            field_name="average_price",
        )
    )

    filled_at = (
        _parse_order_timestamp(
            order.get(
                "last_transaction_at"
            ),
            field_name=(
                "last_transaction_at"
            ),
        )
    )

    return ConfirmedEquityEntryFill(
        account_number=account_number,
        symbol=symbol,
        broker_order_id=(
            broker_order_id
        ),
        ref_id=ref_id,
        filled_quantity=(
            filled_quantity
        ),
        average_fill_price=(
            average_fill_price
        ),
        filled_at=filled_at,
    )


def confirm_and_activate_equity_entry(
    invoker: MCPToolInvoker,
    store: PositionStateStore,
    quote_provider: EquityEntryQuoteProvider,
    *,
    account_number: str,
    symbol: str,
    broker_order_id: str,
    ref_id: str,
) -> PositionRuntimeState | None:
    raw_result = invoker.call_tool(
        "get_equity_orders",
        {
            "account_number": (
                account_number
            ),
            "order_id": (
                broker_order_id
            ),
        },
    )

    fill = (
        decode_confirmed_equity_entry_fill(
            raw_result,
            account_number=(
                account_number
            ),
            symbol=symbol,
            broker_order_id=(
                broker_order_id
            ),
            ref_id=ref_id,
        )
    )

    if fill is None:
        return None

    initial_quote = (
        quote_provider.get_quote(
            symbol
        )
    )

    return activate_filled_equity_entry(
        store,
        fill,
        initial_quote=initial_quote,
    )

def activate_acknowledged_equity_entries(
    invoker: MCPToolInvoker,
    journal: SQLiteEquityEntryPlacementJournal,
    store: PositionStateStore,
    quote_provider: EquityEntryQuoteProvider,
    *,
    account_number: str,
) -> list[PositionRuntimeState]:
    records = journal.list_acknowledged(
        account_number=account_number,
    )

    activated_positions = []

    for record in records:
        if record.broker_order_id is None:
            raise ValueError(
                "acknowledged entry placement "
                "must contain broker_order_id"
            )

        state = (
            confirm_and_activate_equity_entry(
                invoker,
                store,
                quote_provider,
                account_number=(
                    record.account_number
                ),
                symbol=record.symbol,
                broker_order_id=(
                    record.broker_order_id
                ),
                ref_id=record.ref_id,
            )
        )

        # Order still confirmed / queued /
        # partially filled, etc.
        if state is None:
            continue

        journal.transition(
            record.ref_id,
            expected_status=(
                EntryPlacementStatus
                .ACKNOWLEDGED
            ),
            new_status=(
                EntryPlacementStatus
                .ACTIVATED
            ),
        )

        activated_positions.append(
            state
        )

    return activated_positions