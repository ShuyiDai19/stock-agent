from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_order_pagination import (
    extract_robinhood_order_next_cursor,
)
from stock_agent.domain import AssetType


_NEW_YORK = ZoneInfo(
    "America/New_York"
)

_TERMINAL_ORDER_STATES = frozenset(
    {
        "filled",
        "canceled",
        "cancelled",
        "rejected",
        "failed",
        "voided",
    }
)

_SUBMISSION_TIME_FIELDS = (
    "created_at",
    "submitted_at",
    "placed_at",
)


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodOrderActivityReadResult:
    has_open_equity_order: bool
    has_open_option_order: bool
    has_opening_order_today: bool


def _require_text(
    order: dict[str, Any],
    field_name: str,
) -> str:
    value = order.get(
        field_name
    )

    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            "Robinhood order "
            f"{field_name} must be "
            "a nonempty string"
        )

    return value.strip().lower()


def _parse_order_submission_time(
    order: dict[str, Any],
) -> datetime:
    value = None
    field_name = None

    for candidate in (
        _SUBMISSION_TIME_FIELDS
    ):
        candidate_value = order.get(
            candidate
        )

        if candidate_value is not None:
            value = candidate_value
            field_name = candidate
            break

    if (
        field_name is None
        or not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            "Robinhood closed order "
            "must contain a submission "
            "timestamp"
        )

    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError as exc:
        raise ValueError(
            "Robinhood order "
            f"{field_name} is invalid"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset()
        is None
    ):
        raise ValueError(
            "Robinhood order "
            f"{field_name} must be "
            "timezone-aware"
        )

    return parsed


def _is_open_order(
    order: dict[str, Any],
) -> bool:
    state = _require_text(
        order,
        "state",
    )

    # Unknown future broker states are
    # intentionally treated as OPEN.
    return (
        state
        not in _TERMINAL_ORDER_STATES
    )


def _is_opening_order_today(
    order: dict[str, Any],
    *,
    asset_type: AssetType,
    evaluated_at: datetime,
    is_open: bool,
) -> bool:
    try:
        submitted_at = (
            _parse_order_submission_time(
                order
            )
        )
    except ValueError:
        # If this order is already known
        # to be open, preflight will block
        # regardless of its submission date.
        if is_open:
            return False

        # Closed order with unknown submission
        # time cannot safely prove that no
        # opening order occurred today.
        raise

    target_date = (
        evaluated_at
        .astimezone(_NEW_YORK)
        .date()
    )

    submitted_date = (
        submitted_at
        .astimezone(_NEW_YORK)
        .date()
    )

    if submitted_date != target_date:
        return False

    side = _require_text(
        order,
        "side",
    )

    if side not in {
        "buy",
        "sell",
    }:
        raise ValueError(
            "Robinhood order side "
            "is unsupported"
        )

    if asset_type is AssetType.EQUITY:
        # In this strategy, any equity BUY
        # creates or increases exposure and
        # therefore counts as an opening
        # order for the daily-entry gate.
        return side == "buy"

    if asset_type is AssetType.OPTION:
        if side != "buy":
            return False

        position_effect = _require_text(
            order,
            "position_effect",
        )

        if position_effect not in {
            "open",
            "close",
        }:
            raise ValueError(
                "Robinhood option order "
                "position_effect is unsupported"
            )

        return (
            position_effect == "open"
        )

    raise ValueError(
        f"unsupported asset type: "
        f"{asset_type}"
    )


class MCPRobinhoodOrderActivityReader:
    def __init__(
        self,
        invoker: MCPToolInvoker,
        *,
        max_pages: int = 10,
    ) -> None:
        if (
            type(max_pages) is not int
            or max_pages < 1
        ):
            raise ValueError(
                "max_pages must be a "
                "positive integer"
            )

        self._invoker = invoker
        self._max_pages = max_pages

    def _read_orders(
        self,
        *,
        tool_name: str,
        account_number: str,
    ) -> tuple[
        dict[str, Any],
        ...
    ]:
        arguments = {
            "account_number":
                account_number,
        }

        orders = []
        seen_cursors: set[str] = set()

        for _ in range(
            self._max_pages
        ):
            raw_result = (
                self._invoker.call_tool(
                    tool_name,
                    arguments,
                )
            )

            if not isinstance(
                raw_result,
                dict,
            ):
                raise ValueError(
                    "Robinhood order result "
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
                    "Robinhood order result "
                    "must contain data"
                )

            page_orders = data.get(
                "orders"
            )

            if not isinstance(
                page_orders,
                list,
            ):
                raise ValueError(
                    "Robinhood order result "
                    "must contain orders"
                )

            for order in page_orders:
                if not isinstance(
                    order,
                    dict,
                ):
                    raise ValueError(
                        "Robinhood orders "
                        "must be mappings"
                    )

                orders.append(
                    order
                )

            next_cursor = (
                extract_robinhood_order_next_cursor(
                    raw_result
                )
            )

            if next_cursor is None:
                return tuple(
                    orders
                )

            if next_cursor in seen_cursors:
                raise ValueError(
                    "Robinhood order pagination "
                    "cursor repeated"
                )

            seen_cursors.add(
                next_cursor
            )

            arguments = {
                "account_number":
                    account_number,
                "cursor":
                    next_cursor,
            }

        raise ValueError(
            "Robinhood order history reached "
            "maximum page limit"
        )

    def read(
        self,
        *,
        account_number: str,
        evaluated_at: datetime,
    ) -> RobinhoodOrderActivityReadResult:
        if not account_number.strip():
            raise ValueError(
                "account_number must not "
                "be empty"
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

        equity_orders = self._read_orders(
            tool_name="get_equity_orders",
            account_number=account_number,
        )

        option_orders = self._read_orders(
            tool_name="get_option_orders",
            account_number=account_number,
        )

        has_open_equity_order = False
        has_open_option_order = False
        has_opening_order_today = False

        for order in equity_orders:
            is_open = _is_open_order(
                order
            )

            if is_open:
                has_open_equity_order = True

            if _is_opening_order_today(
                order,
                asset_type=AssetType.EQUITY,
                evaluated_at=evaluated_at,
                is_open=is_open,
            ):
                has_opening_order_today = True

        for order in option_orders:
            is_open = _is_open_order(
                order
            )

            if is_open:
                has_open_option_order = True

            if _is_opening_order_today(
                order,
                asset_type=AssetType.OPTION,
                evaluated_at=evaluated_at,
                is_open=is_open,
            ):
                has_opening_order_today = True

        return RobinhoodOrderActivityReadResult(
            has_open_equity_order=(
                has_open_equity_order
            ),
            has_open_option_order=(
                has_open_option_order
            ),
            has_opening_order_today=(
                has_opening_order_today
            ),
        )