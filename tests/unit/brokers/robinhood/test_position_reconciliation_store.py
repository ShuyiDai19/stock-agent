import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from dataclasses import replace

from stock_agent.state.store import (
    ConcurrentStateUpdateError,
)

from stock_agent.brokers.robinhood.position_reconciliation import (
    EquityPositionReconciliationIssue,
    EquityPositionReconciliationOutcome,
)
from stock_agent.brokers.robinhood.position_reconciliation_policy import (
    EquityPositionReconciliationAction,
    EquityPositionReconciliationDecision,
)
from stock_agent.brokers.robinhood.position_reconciliation_store import (
    EquityPositionReconciliationApplyStatus,
    apply_equity_position_reconciliation,
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

_NOW = datetime(
    2026,
    9,
    17,
    tzinfo=timezone.utc,
)


def make_local_state(
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
) -> RobinhoodEquityPositionSnapshot:
    return RobinhoodEquityPositionSnapshot(
        symbol="AAPL",
        quantity=Decimal("1"),
        intraday_quantity=Decimal("0"),
        average_buy_price=Decimal("100"),
        shares_available_for_sells=Decimal("1"),
        position_type=(
            RobinhoodEquityPositionType.LONG
        ),
    )

class EquityPositionReconciliationStoreTests(
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

    def test_mark_reconciled_updates_timestamp_and_version(
        self,
    ) -> None:
        state = make_local_state()
        self.store.insert(state)

        reconciled_at = (
            _NOW + timedelta(minutes=5)
        )

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=state,
            broker_position=(
                make_broker_position()
            ),
            issues=frozenset(),
        )

        decision = EquityPositionReconciliationDecision(
            outcome=outcome,
            action=(
                EquityPositionReconciliationAction
                .MARK_RECONCILED
            ),
        )

        result = (
            apply_equity_position_reconciliation(
                store=self.store,
                decision=decision,
                reconciled_at=reconciled_at,
            )
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

        self.assertEqual(
            result.status,
            EquityPositionReconciliationApplyStatus
            .UPDATED,
        )

    def test_mismatch_marks_position_reconciliation_required(
        self,
    ) -> None:
        state = make_local_state()
        self.store.insert(state)

        reconciled_at = (
            _NOW + timedelta(minutes=5)
        )

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=state,
            broker_position=(
                make_broker_position()
            ),
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .QUANTITY_MISMATCH,
                }
            ),
        )

        decision = EquityPositionReconciliationDecision(
            outcome=outcome,
            action=(
                EquityPositionReconciliationAction
                .REQUIRE_RECONCILIATION
            ),
        )

        apply_equity_position_reconciliation(
            store=self.store,
            decision=decision,
            reconciled_at=reconciled_at,
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertIsNotNone(
            persisted
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus
            .RECONCILIATION_REQUIRED,
        )

        self.assertEqual(
            persisted.version,
            state.version + 1,
        )

    def test_broker_only_review_does_not_modify_store(
        self,
    ) -> None:
        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=None,
            broker_position=(
                make_broker_position()
            ),
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .LOCAL_POSITION_MISSING,
                }
            ),
        )

        decision = EquityPositionReconciliationDecision(
            outcome=outcome,
            action=(
                EquityPositionReconciliationAction
                .BROKER_ONLY_REVIEW
            ),
        )

        result = (
            apply_equity_position_reconciliation(
                store=self.store,
                decision=decision,
                reconciled_at=_NOW,
            )
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

        self.assertEqual(
            result.status,
            EquityPositionReconciliationApplyStatus
            .NO_STORE_CHANGE,
        )

        self.assertIsNone(
            result.updated_state
        )

    def test_stale_decision_is_rejected_by_store(
        self,
    ) -> None:
        state = make_local_state()
        self.store.insert(state)

        newer_state = replace(
            state,
            last_reconciled_at=(
                _NOW + timedelta(minutes=1)
            ),
            version=state.version + 1,
        )

        self.store.update(
            newer_state,
            expected_version=state.version,
        )

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=state,
            broker_position=(
                make_broker_position()
            ),
            issues=frozenset(),
        )

        decision = EquityPositionReconciliationDecision(
            outcome=outcome,
            action=(
                EquityPositionReconciliationAction
                .MARK_RECONCILED
            ),
        )

        with self.assertRaises(
            ConcurrentStateUpdateError
        ):
            apply_equity_position_reconciliation(
                store=self.store,
                decision=decision,
                reconciled_at=(
                    _NOW + timedelta(minutes=5)
                ),
            )

    def test_sync_closing_quantity_updates_remaining_quantity_and_stays_closing(
        self,
    ) -> None:
        local_state = replace(
            make_local_state(
                status=PositionStateStatus.CLOSING,
            ),
            remaining_quantity=Decimal("1"),
        )

        broker_position = replace(
            make_broker_position(),
            quantity=Decimal("0.4"),
            shares_available_for_sells=Decimal("0"),
        )

        self.store.insert(
            local_state
        )

        reconciled_at = (
            _NOW + timedelta(minutes=5)
        )

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=local_state,
            broker_position=broker_position,
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .QUANTITY_MISMATCH
                }
            ),
        )

        decision = (
            EquityPositionReconciliationDecision(
                outcome=outcome,
                action=(
                    EquityPositionReconciliationAction
                    .SYNC_CLOSING_QUANTITY
                ),
            )
        )

        result = apply_equity_position_reconciliation(
            store=self.store,
            decision=decision,
            reconciled_at=reconciled_at,
        )

        self.assertEqual(
            result.status,
            EquityPositionReconciliationApplyStatus
            .UPDATED,
        )

        updated_state = result.updated_state

        self.assertIsNotNone(
            updated_state
        )

        self.assertEqual(
            updated_state.remaining_quantity,
            Decimal("0.4"),
        )

        self.assertEqual(
            updated_state.status,
            PositionStateStatus.CLOSING,
        )

        self.assertEqual(
            updated_state.version,
            local_state.version + 1,
        )

        persisted = self.store.get(
            local_state.position_id
        )

        self.assertIsNotNone(
            persisted
        )

        self.assertEqual(
            persisted.remaining_quantity,
            Decimal("0.4"),
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.CLOSING,
        )