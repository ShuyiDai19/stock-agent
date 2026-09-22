from dataclasses import dataclass
from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_position_pagination import (
    RobinhoodPositionPaginationError,
    extract_robinhood_position_next_cursor,
)


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodOptionExposureReadResult:
    has_open_position: bool


def _decode_option_position_presence(
    payload: Any,
) -> bool:
    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Robinhood option position result "
            "must be a mapping"
        )

    data = payload.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood option position result "
            "must contain data"
        )

    positions = data.get(
        "positions"
    )

    if not isinstance(
        positions,
        list,
    ):
        raise ValueError(
            "data.positions must be a list"
        )

    for index, position in enumerate(
        positions
    ):
        if not isinstance(
            position,
            dict,
        ):
            raise ValueError(
                "data.positions"
                f"[{index}] must be a mapping"
            )

    return bool(
        positions
    )


class MCPRobinhoodOptionExposureReader:
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
    ) -> RobinhoodOptionExposureReadResult:
        if not isinstance(
            account_number,
            str,
        ):
            raise TypeError(
                "account_number must "
                "be a string"
            )

        if not account_number.strip():
            raise ValueError(
                "account_number cannot "
                "be empty"
            )

        arguments = {
            "account_number":
                account_number,
        }

        seen_cursors: set[str] = set()

        for _ in range(
            self._max_pages
        ):
            payload = (
                self._invoker.call_tool(
                    "get_option_positions",
                    arguments,
                )
            )

            if (
                _decode_option_position_presence(
                    payload
                )
            ):
                return (
                    RobinhoodOptionExposureReadResult(
                        has_open_position=True
                    )
                )

            cursor = (
                extract_robinhood_position_next_cursor(
                    payload
                )
            )

            if cursor is None:
                return (
                    RobinhoodOptionExposureReadResult(
                        has_open_position=False
                    )
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