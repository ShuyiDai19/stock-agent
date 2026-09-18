import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.position_reader import (
    RobinhoodEquityPositionReadResult,
)
from stock_agent.brokers.robinhood.position_reconciliation_policy import (
    EquityPositionReconciliationAction,
)
from stock_agent.brokers.robinhood.position_reconciliation_service import (
    EquityPositionReconciliationService,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
    RobinhoodEquityPositionType,
)
from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)

class FakeEquityPositionReader:
    def __init__(
        self,
        positions,
    ) -> None:
        self.positions = tuple(
            positions
        )
        self.calls = []

    def read(
        self,
        *,
        account_number: str,
    ) -> RobinhoodEquityPositionReadResult:
        self.calls.append(
            account_number
        )

        return RobinhoodEquityPositionReadResult(
            positions=self.positions
        )

_NOW = datetime(
    2026,
    9,
    17,
    tzinfo=timezone.utc,
)


def make_local_state(
    *,
    quantity: Decimal = Decimal("1"),
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
        remaining_quantity=quantity,
        opened_at=_NOW,
        highest_executable_bid=Decimal("100"),
        trailing_armed=False,
        trailing_armed_at=None,
        activation_gain_ratio=Decimal("0.04"),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
        status=status,
    )


def make_broker_position(
    *,
    quantity: Decimal = Decimal("1"),
    sellable: Decimal = Decimal("1"),
) -> RobinhoodEquityPositionSnapshot:
    return RobinhoodEquityPositionSnapshot(
        symbol="AAPL",
        quantity=quantity,
        intraday_quantity=Decimal("0"),
        average_buy_price=Decimal("100"),
        shares_available_for_sells=sellable,
        position_type=(
            RobinhoodEquityPositionType.LONG
        ),
    )

class EquityPositionReconciliationServiceTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        self.store = SQLitePositionStateStore(
            Path(
                self.temp_directory.name
            )
            / "positions.sqlite3"
        )

        self.store.initialize()

    def tearDown(
        self,
    ) -> None:
        self.temp_directory.cleanup()

    def test_run_reconciles_matching_position(
        self,
    ) -> None:
        state = make_local_state()
        self.store.insert(state)

        reader = FakeEquityPositionReader(
            [
                make_broker_position()
            ]
        )

        service = (
            EquityPositionReconciliationService(
                reader,
                self.store,
            )
        )

        reconciled_at = (
            _NOW + timedelta(minutes=5)
        )

        result = service.run(
            account_number="agentic-account",
            reconciled_at=reconciled_at,
        )

        self.assertEqual(
            reader.calls,
            [
                "agentic-account"
            ],
        )

        self.assertEqual(
            len(result.outcomes),
            1,
        )

        self.assertEqual(
            result.decisions[0].action,
            EquityPositionReconciliationAction
            .MARK_RECONCILED,
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertIsNotNone(
            persisted
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            persisted.last_reconciled_at,
            reconciled_at,
        )

        self.assertEqual(
            persisted.version,
            state.version + 1,
        )

    def test_run_marks_quantity_mismatch_for_reconciliation(
        self,
    ) -> None:
        state = make_local_state(
            quantity=Decimal("1")
        )
        self.store.insert(state)

        reader = FakeEquityPositionReader(
            [
                make_broker_position(
                    quantity=Decimal("0.5"),
                    sellable=Decimal("0.5"),
                )
            ]
        )

        service = (
            EquityPositionReconciliationService(
                reader,
                self.store,
            )
        )

        result = service.run(
            account_number="agentic-account",
            reconciled_at=(
                _NOW + timedelta(minutes=5)
            ),
        )

        self.assertEqual(
            result.decisions[0].action,
            EquityPositionReconciliationAction
            .REQUIRE_RECONCILIATION,
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus
            .RECONCILIATION_REQUIRED,
        )

    def test_run_does_not_adopt_broker_only_position(
        self,
    ) -> None:
        reader = FakeEquityPositionReader(
            [
                make_broker_position()
            ]
        )

        service = (
            EquityPositionReconciliationService(
                reader,
                self.store,
            )
        )

        result = service.run(
            account_number="agentic-account",
            reconciled_at=_NOW,
        )

        self.assertEqual(
            result.decisions[0].action,
            EquityPositionReconciliationAction
            .BROKER_ONLY_REVIEW,
        )

        self.assertEqual(
            result.applications[0]
            .updated_state,
            None,
        )

        states = self.store.list_by_status(
            account_number="agentic-account",
            statuses=(
                PositionStateStatus.ACTIVE,
                PositionStateStatus.CLOSING,
                PositionStateStatus
                .RECONCILIATION_REQUIRED,
            ),
        )

        self.assertEqual(
            states,
            [],
        )

    def test_run_does_not_auto_reactivate_reconciliation_required_state(
        self,
    ) -> None:
        state = make_local_state(
            status=(
                PositionStateStatus
                .RECONCILIATION_REQUIRED
            )
        )
        self.store.insert(state)

        reader = FakeEquityPositionReader(
            [
                make_broker_position()
            ]
        )

        service = (
            EquityPositionReconciliationService(
                reader,
                self.store,
            )
        )

        service.run(
            account_number="agentic-account",
            reconciled_at=(
                _NOW + timedelta(minutes=5)
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