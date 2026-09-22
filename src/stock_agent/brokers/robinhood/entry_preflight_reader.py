from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp_order_activity_reader import (
    MCPRobinhoodOrderActivityReader,
)
from stock_agent.brokers.robinhood.position_reader import (
    MCPRobinhoodEquityPositionReader,
)
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightSnapshot,
)
from stock_agent.brokers.robinhood.entry_funds import (
    RobinhoodEntryFundsReader,
    RobinhoodEntryFundsSnapshot,
)
from stock_agent.brokers.robinhood.option_exposure_reader import (
    MCPRobinhoodOptionExposureReader,
)



class RobinhoodEquityEntryPreflightReader:
    def __init__(
        self,
        position_reader,
        option_exposure_reader,
        order_activity_reader,
        funds_reader,
    ) -> None:
        self._position_reader = (
            position_reader
        )
        self._option_exposure_reader = (
            option_exposure_reader
        )
        self._order_activity_reader = (
            order_activity_reader
        )
        self._funds_reader = (
            funds_reader
        )

    def read(
        self,
        *,
        account_number: str,
        evaluated_at: datetime,
    ) -> EquityEntryPreflightSnapshot:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
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

        positions = (
            self._position_reader.read(
                account_number=(
                    account_number
                )
            )
        )

        option_exposure = (
            self._option_exposure_reader.read(
                account_number=account_number
            )
        )

        order_activity = (
            self._order_activity_reader.read(
                account_number=(
                    account_number
                ),
                evaluated_at=(
                    evaluated_at
                ),
            )
        )

        funds = (
            self._funds_reader.read(
                account_number=(
                    account_number
                )
            )
        )

        has_equity_position = any(
            position.quantity > Decimal("0")
            for position in positions.positions
        )

        has_existing_position = (
            has_equity_position
            or option_exposure.has_open_position
        )

        return EquityEntryPreflightSnapshot(
            has_existing_position=(
                has_existing_position
            ),
            has_open_equity_order=(
                order_activity
                .has_open_equity_order
            ),
            has_open_option_order=(
                order_activity
                .has_open_option_order
            ),
            has_opening_order_today=(
                order_activity
                .has_opening_order_today
            ),
            buying_power=(
                funds.buying_power
            ),
            cash=funds.cash,
        )