import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from stock_agent.brokers.robinhood.journal_position_close_service import (
    JournalBackedEquityPositionCloseService,
)
from stock_agent.brokers.robinhood.mcp_order_execution_reader import (
    MCPRobinhoodEquityOrderExecutionReader,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAcknowledgement,
    PlacementAttemptRecord,
    PlacementAttemptStatus,
    SQLitePlacementAttemptJournal,
)
from stock_agent.brokers.robinhood.position_close_service import (
    EquityPositionCloseConfirmationService,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)


_NOW = datetime(
    2026,
    9,
    18,
    22,
    0,
    tzinfo=timezone.utc,
)

_POSITION_ID = "position-1"

_REF_ID = (
    "00000000-0000-4000-8000-000000000001"
)

_BROKER_ORDER_ID = "broker-order-1"


class FakeMCPToolInvoker:
    def __init__(
        self,
    ) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append(
            (
                tool_name,
                arguments,
            )
        )

        return {
            "data": {
                "orders": [
                    {
                        "id": _BROKER_ORDER_ID,
                        "ref_id": _REF_ID,
                        "state": "filled",
                        "quantity": "1",
                    }
                ]
            }
        }


def make_closing_position(
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id=_POSITION_ID,
        account_number="agentic-account",
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        opening_order_id="opening-order-1",
        entry_price=Decimal("100"),
        remaining_quantity=Decimal("1"),
        opened_at=_NOW,
        highest_executable_bid=Decimal("105"),
        trailing_armed=True,
        trailing_armed_at=_NOW,
        activation_gain_ratio=Decimal("0.04"),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
        status=PositionStateStatus.CLOSING,
    )


def make_placement_attempt(
) -> PlacementAttemptRecord:
    return PlacementAttemptRecord(
        submission=RobinhoodExitSubmission(
            request=RobinhoodExitOrderRequest(
                position_id=_POSITION_ID,
                account_number="agentic-account",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("1"),
                action=(
                    RobinhoodExitAction
                    .EQUITY_SELL
                ),
                option_id=None,
            ),
            ref_id=_REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        ),
        placement_attempted_at=_NOW,
    )


class PositionCloseRecoveryPipelineTests(
    unittest.TestCase
):
    def test_acknowledged_filled_order_closes_persisted_position(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(
                directory
            )

            position_store = (
                SQLitePositionStateStore(
                    directory_path
                    / "positions.sqlite3"
                )
            )

            position_store.initialize()

            original_state = (
                make_closing_position()
            )

            position_store.insert(
                original_state
            )

            placement_journal = (
                SQLitePlacementAttemptJournal(
                    directory_path
                    / "placement.sqlite3"
                )
            )

            placement_journal.initialize()

            placement_attempt = (
                make_placement_attempt()
            )

            placement_journal.insert(
                placement_attempt
            )

            placement_journal.transition(
                _REF_ID,
                expected_status=(
                    PlacementAttemptStatus
                    .PREPARED
                ),
                new_status=(
                    PlacementAttemptStatus
                    .SUBMITTING
                ),
            )

            placement_journal.acknowledge(
                _REF_ID,
                PlacementAcknowledgement(
                    broker_order_id=(
                        _BROKER_ORDER_ID
                    ),
                    acknowledged_at=(
                        _NOW
                        + timedelta(seconds=1)
                    ),
                ),
            )

            invoker = FakeMCPToolInvoker()

            execution_reader = (
                MCPRobinhoodEquityOrderExecutionReader(
                    invoker
                )
            )

            close_service = (
                EquityPositionCloseConfirmationService(
                    position_store,
                    execution_reader,
                    clock=lambda: (
                        _NOW
                        + timedelta(minutes=1)
                    ),
                )
            )

            pipeline = (
                JournalBackedEquityPositionCloseService(
                    placement_journal,
                    close_service,
                )
            )

            result = pipeline.confirm_if_filled(
                position_id=_POSITION_ID
            )

            self.assertIsNotNone(
                result
            )

            self.assertEqual(
                result.status,
                PositionStateStatus.CLOSED,
            )

            self.assertEqual(
                result.remaining_quantity,
                Decimal("0"),
            )

            self.assertEqual(
                result.version,
                original_state.version + 1,
            )

            persisted = (
                position_store.get(
                    _POSITION_ID
                )
            )

            self.assertIsNotNone(
                persisted
            )

            self.assertEqual(
                persisted.status,
                PositionStateStatus.CLOSED,
            )

            self.assertEqual(
                persisted.remaining_quantity,
                Decimal("0"),
            )

            self.assertEqual(
                persisted.version,
                original_state.version + 1,
            )

            self.assertEqual(
                invoker.calls,
                [
                    (
                        "get_equity_orders",
                        {
                            "account_number": (
                                "agentic-account"
                            ),
                            "order_id": (
                                _BROKER_ORDER_ID
                            ),
                        },
                    )
                ],
            )


if __name__ == "__main__":
    unittest.main()