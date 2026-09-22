from dataclasses import dataclass

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_position_decoder import (
    decode_robinhood_equity_positions,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
)
from stock_agent.brokers.robinhood.mcp_position_pagination import (
    RobinhoodPositionPaginationError,
    extract_robinhood_position_next_cursor,
)



@dataclass(frozen=True)
class RobinhoodEquityPositionReadResult:
    positions: tuple[
        RobinhoodEquityPositionSnapshot,
        ...
    ]



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

            cursor = (
                extract_robinhood_position_next_cursor(
                    payload
                )
            )

            if cursor is None:
                return (
                    RobinhoodEquityPositionReadResult(
                        positions=tuple(
                            positions
                        )
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