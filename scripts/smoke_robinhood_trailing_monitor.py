import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.connection import (
    open_robinhood_mcp_invoker,
)
from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
)
from stock_agent.brokers.robinhood.position_reader import (
    MCPRobinhoodEquityPositionReader,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionType,
)
from stock_agent.domain import AssetType
from stock_agent.monitoring.trailing_stop_monitor import (
    TrailingStopMonitor,
)
from stock_agent.risk import (
    TrailingStopDecision,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)


_SMOKE_BASE_TIME = datetime(
    2000,
    1,
    1,
    tzinfo=timezone.utc,
)


def main() -> None:
    account_number = os.environ.get(
        "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER"
    )

    if not account_number:
        raise RuntimeError(
            "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER "
            "must be set"
        )

    symbol = os.environ.get(
        "ROBINHOOD_MONITOR_SMOKE_SYMBOL",
        "AAPL",
    ).strip().upper()

    if not symbol:
        raise RuntimeError(
            "ROBINHOOD_MONITOR_SMOKE_SYMBOL "
            "must not be empty"
        )

    with open_robinhood_mcp_invoker(
        allowed_account_number=account_number,
        startup_timeout_seconds=300.0,
    ) as invoker:
        position_reader = (
            MCPRobinhoodEquityPositionReader(
                invoker
            )
        )

        broker_positions = (
            position_reader.read(
                account_number=account_number
            ).positions
        )

        matches = [
            position
            for position in broker_positions
            if position.symbol == symbol
        ]

        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one open "
                f"{symbol} broker position, "
                f"found {len(matches)}"
            )

        broker_position = matches[0]

        if (
            broker_position.position_type
            is not RobinhoodEquityPositionType.LONG
        ):
            raise RuntimeError(
                "smoke test requires a long "
                "equity position"
            )

        if (
            broker_position.average_buy_price
            is None
        ):
            raise RuntimeError(
                "average_buy_price is unavailable"
            )

        if broker_position.quantity <= 0:
            raise RuntimeError(
                "broker position quantity "
                "must be positive"
            )

        quote_provider = (
            MCPRobinhoodEquityQuoteProvider(
                invoker
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePositionStateStore(
                Path(directory)
                / "positions.sqlite3"
            )
            store.initialize()

            state = PositionRuntimeState(
                position_id=(
                    "smoke-only-position"
                ),
                account_number=account_number,
                asset_type=AssetType.EQUITY,
                symbol=symbol,

                # Deliberately synthetic and confined
                # to this temporary database.
                opening_order_id=(
                    "smoke-only-opening-order"
                ),

                entry_price=(
                    broker_position
                    .average_buy_price
                ),
                remaining_quantity=(
                    broker_position.quantity
                ),
                opened_at=_SMOKE_BASE_TIME,

                highest_executable_bid=(
                    broker_position
                    .average_buy_price
                ),
                trailing_armed=False,
                trailing_armed_at=None,

                activation_gain_ratio=(
                    Decimal("0.04")
                ),
                drawdown_ratio=(
                    Decimal("0.02")
                ),

                last_quote_at=_SMOKE_BASE_TIME,
                last_reconciled_at=(
                    _SMOKE_BASE_TIME
                ),
                status=(
                    PositionStateStatus.ACTIVE
                ),

                # Critical safety property:
                # we do not know the historical
                # executable high for this imported
                # brokerage position.
                historical_high_unknown=True,
            )

            store.insert(
                state
            )

            monitor = TrailingStopMonitor(
                store,
                quote_provider,
            )

            evaluation = (
                monitor.process_position(
                    state.position_id
                )
            )

            persisted = store.get(
                state.position_id
            )

            if persisted is None:
                raise AssertionError(
                    "temporary position disappeared"
                )

            print(
                "Real Robinhood trailing-monitor "
                "smoke completed."
            )

            print(
                "Symbol:",
                symbol,
            )

            print(
                "Broker quantity:",
                broker_position.quantity,
            )

            print(
                "Broker average cost:",
                broker_position
                .average_buy_price,
            )

            print(
                "Observed executable bid:",
                persisted
                .highest_executable_bid,
            )

            print(
                "Quote observed at:",
                persisted.last_quote_at
                .isoformat(),
            )

            print(
                "Trailing armed:",
                persisted.trailing_armed,
            )

            print(
                "Historical high unknown:",
                persisted
                .historical_high_unknown,
            )

            print(
                "Decision:",
                evaluation.decision.value,
            )

            if (
                evaluation.decision
                is not TrailingStopDecision.HOLD
            ):
                raise AssertionError(
                    "historical-high-unknown "
                    "smoke must not produce EXIT"
                )

            if not (
                persisted
                .historical_high_unknown
            ):
                raise AssertionError(
                    "historical_high_unknown "
                    "was unexpectedly cleared"
                )

            if (
                persisted.status
                is not PositionStateStatus.ACTIVE
            ):
                raise AssertionError(
                    "monitor must not close "
                    "the position state"
                )

            print(
                "Verified: temporary state only."
            )

            print(
                "Verified: no exit order submitted."
            )


if __name__ == "__main__":
    main()