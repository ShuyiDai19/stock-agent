import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from stock_agent.orchestration.execution_state import (
    ExecutionStateTransitionError,
    apply_execution_result_to_position_state,
)
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
    tzinfo=timezone.utc,
)


def make_state(
    *,
    status: PositionStateStatus = (
        PositionStateStatus.ACTIVE
    ),
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id="position-1",
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
        status=status,
    )


def make_result(
    status: ExecutionStatus,
) -> ExecutionResult:
    return ExecutionResult(
        position_id="position-1",
        status=status,
        submitted_at=_NOW,
        broker_order_id=(
            "broker-order-1"
            if status is ExecutionStatus.SUBMITTED
            else None
        ),
    )

class ExecutionStateTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        self.store = SQLitePositionStateStore(
            Path(self.temp_directory.name)
            / "positions.sqlite3"
        )
        self.store.initialize()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_submitted_exit_marks_active_position_closing(
        self,
    ) -> None:
        state = make_state()
        self.store.insert(state)

        updated = (
            apply_execution_result_to_position_state(
                self.store,
                make_result(
                    ExecutionStatus.SUBMITTED
                ),
            )
        )

        self.assertIsNotNone(updated)

        self.assertEqual(
            updated.status,
            PositionStateStatus.CLOSING,
        )

        self.assertEqual(
            updated.version,
            state.version + 1,
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.CLOSING,
        )

    def test_previewed_exit_does_not_change_state(
        self,
    ) -> None:
        state = make_state()
        self.store.insert(state)

        result = (
            apply_execution_result_to_position_state(
                self.store,
                make_result(
                    ExecutionStatus.PREVIEWED
                ),
            )
        )

        self.assertIsNone(result)

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            persisted.version,
            state.version,
        )

    def test_submitted_exit_is_idempotent_when_already_closing(
        self,
    ) -> None:
        state = make_state(
            status=PositionStateStatus.CLOSING
        )
        self.store.insert(state)

        updated = (
            apply_execution_result_to_position_state(
                self.store,
                make_result(
                    ExecutionStatus.SUBMITTED
                ),
            )
        )

        self.assertEqual(
            updated,
            state,
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.version,
            state.version,
        )

    def test_submitted_exit_does_not_override_reconciliation_required(
        self,
    ) -> None:
        state = make_state(
            status=(
                PositionStateStatus
                .RECONCILIATION_REQUIRED
            )
        )
        self.store.insert(state)

        with self.assertRaises(
            ExecutionStateTransitionError
        ):
            apply_execution_result_to_position_state(
                self.store,
                make_result(
                    ExecutionStatus.SUBMITTED
                ),
            )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus
            .RECONCILIATION_REQUIRED,
        )