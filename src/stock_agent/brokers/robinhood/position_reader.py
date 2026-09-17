from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_position_decoder import (
    decode_robinhood_equity_positions,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
)


class RobinhoodPositionPaginationError(
    ValueError
):
    pass


@dataclass(frozen=True)
class RobinhoodEquityPositionReadResult:
    positions: tuple[
        RobinhoodEquityPositionSnapshot,
        ...
    ]


_MISSING = object()


def _extract_next_url(
    payload: dict[str, Any],
) -> str | None:
    top_level_next = payload.get(
        "next",
        _MISSING,
    )

    data = payload.get("data")

    if isinstance(data, dict):
        nested_next = data.get(
            "next",
            _MISSING,
        )
    else:
        nested_next = _MISSING

    if (
        top_level_next is _MISSING
        and nested_next is _MISSING
    ):
        return None

    if (
        top_level_next is not _MISSING
        and nested_next is not _MISSING
        and top_level_next != nested_next
    ):
        raise RobinhoodPositionPaginationError(
            "conflicting pagination metadata"
        )

    next_value = (
        top_level_next
        if top_level_next is not _MISSING
        else nested_next
    )

    if next_value is None:
        return None

    if not isinstance(
        next_value,
        str,
    ):
        raise RobinhoodPositionPaginationError(
            "next must be a string or null"
        )

    next_url = next_value.strip()

    if not next_url:
        raise RobinhoodPositionPaginationError(
            "next must not be empty"
        )

    return next_url


def _extract_cursor(
    next_url: str,
) -> str:
    parsed = urlparse(
        next_url
    )

    if parsed.scheme != "https":
        raise RobinhoodPositionPaginationError(
            "next must use https"
        )

    query = parse_qs(
        parsed.query,
        keep_blank_values=True,
    )

    cursors = query.get(
        "cursor"
    )

    if (
        cursors is None
        or len(cursors) != 1
        or not cursors[0].strip()
    ):
        raise RobinhoodPositionPaginationError(
            "next must contain exactly "
            "one non-empty cursor"
        )

    return cursors[0]


class MCPRobinhoodEquityPositionReader:
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

    def read(
        self,
        *,
        account_number: str,
    ) -> RobinhoodEquityPositionReadResult:
        if not account_number.strip():
            raise ValueError(
                "account_number must not be empty"
            )

        arguments = {
            "account_number":
                account_number,
        }

        positions = []
        seen_cursors: set[str] = set()

        for _ in range(
            self._max_pages
        ):
            payload = (
                self._invoker.call_tool(
                    "get_equity_positions",
                    arguments,
                )
            )

            positions.extend(
                decode_robinhood_equity_positions(
                    payload
                )
            )

            next_url = _extract_next_url(
                payload
            )

            if next_url is None:
                return (
                    RobinhoodEquityPositionReadResult(
                        positions=tuple(
                            positions
                        )
                    )
                )

            cursor = _extract_cursor(
                next_url
            )

            if cursor in seen_cursors:
                raise (
                    RobinhoodPositionPaginationError(
                        "repeated pagination cursor"
                    )
                )

            seen_cursors.add(
                cursor
            )

            arguments = {
                "account_number":
                    account_number,
                "cursor":
                    cursor,
            }

        raise RobinhoodPositionPaginationError(
            "maximum page limit reached "
            "before pagination completed"
        )