from decimal import Decimal, InvalidOperation
from typing import Any

from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.domain.enums import (
    OrderStatus,
)


def _parse_positive_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string"
        )

    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            f"{field_name} must be a valid decimal"
        ) from exc

    if not parsed.is_finite():
        raise ValueError(
            f"{field_name} must be finite"
        )

    if parsed <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero"
        )

    return parsed


def decode_robinhood_filled_order(
    raw_order: Any,
    *,
    expected_broker_order_id: str,
    expected_ref_id: str,
) -> RobinhoodOrderExecutionSnapshot | None:
    if not expected_broker_order_id.strip():
        raise ValueError(
            "expected_broker_order_id cannot be empty"
        )

    if not expected_ref_id.strip():
        raise ValueError(
            "expected_ref_id cannot be empty"
        )

    if not isinstance(raw_order, dict):
        raise ValueError(
            "Robinhood order must be a mapping"
        )

    broker_order_id = raw_order.get(
        "id"
    )

    if (
        not isinstance(broker_order_id, str)
        or not broker_order_id.strip()
    ):
        raise ValueError(
            "Robinhood order must contain id"
        )

    if (
        broker_order_id
        != expected_broker_order_id
    ):
        raise ValueError(
            "Robinhood order id does not match "
            "expected broker order id"
        )

    ref_id = raw_order.get(
        "ref_id"
    )

    if (
        not isinstance(ref_id, str)
        or not ref_id.strip()
    ):
        raise ValueError(
            "Robinhood order must contain ref_id"
        )

    if ref_id != expected_ref_id:
        raise ValueError(
            "Robinhood order ref_id does not match "
            "expected ref_id"
        )

    state = raw_order.get(
        "state"
    )

    if (
        not isinstance(state, str)
        or not state.strip()
    ):
        raise ValueError(
            "Robinhood order must contain state"
        )

    # Only an explicit broker FILLED state is
    # accepted as full-fill confirmation.
    #
    # QUEUED / CONFIRMED / PARTIALLY_FILLED /
    # CANCELLED / unknown future broker states
    # are intentionally not interpreted here.
    if state != OrderStatus.FILLED.value:
        return None

    quantity = _parse_positive_decimal(
        raw_order.get("quantity"),
        field_name="quantity",
    )

    return RobinhoodOrderExecutionSnapshot(
        broker_order_id=broker_order_id,
        ref_id=ref_id,
        status=OrderStatus.FILLED,
        quantity=quantity,
        filled_quantity=quantity,
    )