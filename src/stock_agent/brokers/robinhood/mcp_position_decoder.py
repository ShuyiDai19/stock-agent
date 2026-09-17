from decimal import Decimal, InvalidOperation
from typing import Any

from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
    RobinhoodEquityPositionType,
)


class RobinhoodPositionDecodeError(
    ValueError
):
    pass


def _require_dict(
    value: Any,
    *,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RobinhoodPositionDecodeError(
            f"{field} must be an object"
        )

    return value


def _require_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise RobinhoodPositionDecodeError(
            f"{field} must be a string"
        )

    value = value.strip()

    if not value:
        raise RobinhoodPositionDecodeError(
            f"{field} must not be empty"
        )

    return value


def _decode_decimal(
    value: Any,
    *,
    field: str,
) -> Decimal:
    raw = _require_string(
        value,
        field=field,
    )

    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise RobinhoodPositionDecodeError(
            f"{field} must be a decimal"
        ) from exc

    if not result.is_finite():
        raise RobinhoodPositionDecodeError(
            f"{field} must be finite"
        )

    return result


def decode_robinhood_equity_positions(
    payload: dict[str, Any],
) -> tuple[
    RobinhoodEquityPositionSnapshot,
    ...,
]:
    data = _require_dict(
        payload.get("data"),
        field="data",
    )

    positions = data.get(
        "positions"
    )

    if not isinstance(
        positions,
        list,
    ):
        raise RobinhoodPositionDecodeError(
            "data.positions must be a list"
        )

    decoded = []

    for index, raw_position in enumerate(
        positions
    ):
        field_prefix = (
            f"data.positions[{index}]"
        )

        position = _require_dict(
            raw_position,
            field=field_prefix,
        )

        symbol = _require_string(
            position.get("symbol"),
            field=f"{field_prefix}.symbol",
        )

        quantity = _decode_decimal(
            position.get("quantity"),
            field=f"{field_prefix}.quantity",
        )

        intraday_quantity = _decode_decimal(
            position.get(
                "intraday_quantity"
            ),
            field=(
                f"{field_prefix}."
                "intraday_quantity"
            ),
        )

        raw_average_buy_price = (
            position.get(
                "average_buy_price"
            )
        )

        average_buy_price = (
            None
            if raw_average_buy_price is None
            else _decode_decimal(
                raw_average_buy_price,
                field=(
                    f"{field_prefix}."
                    "average_buy_price"
                ),
            )
        )

        shares_available_for_sells = (
            _decode_decimal(
                position.get(
                    "shares_available_for_sells"
                ),
                field=(
                    f"{field_prefix}."
                    "shares_available_for_sells"
                ),
            )
        )

        raw_type = _require_string(
            position.get("type"),
            field=f"{field_prefix}.type",
        )

        try:
            position_type = (
                RobinhoodEquityPositionType(
                    raw_type
                )
            )
        except ValueError as exc:
            raise RobinhoodPositionDecodeError(
                f"{field_prefix}.type "
                f"is unsupported: {raw_type!r}"
            ) from exc

        try:
            snapshot = (
                RobinhoodEquityPositionSnapshot(
                    symbol=symbol,
                    quantity=quantity,
                    intraday_quantity=(
                        intraday_quantity
                    ),
                    average_buy_price=(
                        average_buy_price
                    ),
                    shares_available_for_sells=(
                        shares_available_for_sells
                    ),
                    position_type=(
                        position_type
                    ),
                )
            )
        except ValueError as exc:
            raise RobinhoodPositionDecodeError(
                f"invalid {field_prefix}: {exc}"
            ) from exc

        decoded.append(
            snapshot
        )

    return tuple(decoded)