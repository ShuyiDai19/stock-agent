import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from stock_agent.brokers.robinhood.equity_exit_reconciler import (
    RobinhoodEquityExitReconciler,
    RobinhoodEquityExitReconciliationError,
)
from stock_agent.brokers.robinhood.exit_state_reconciliation import (
    EquityExitStateReconciler,
)
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
from stock_agent.monitoring import (
    TrailingStopMonitor,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)
from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.domain import (
    AssetType,
    OrderStatus,
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

class PendingEquityOrderExecutionReader:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def read(
        self,
        *,
        account_number: str,
        broker_order_id: str,
        ref_id: str,
    ):
        self.calls.append(
            (
                account_number,
                broker_order_id,
                ref_id,
            )
        )

        # The closing order exists, but a full
        # fill has not yet been confirmed.
        return None

class FilledEquityOrderExecutionReader:
    def __init__(
        self,
        *,
        quantity: Decimal,
    ) -> None:
        self._quantity = quantity
        self.calls = []

    def read(
        self,
        *,
        account_number: str,
        broker_order_id: str,
        ref_id: str,
    ) -> RobinhoodOrderExecutionSnapshot:
        self.calls.append(
            (
                account_number,
                broker_order_id,
                ref_id,
            )
        )

        return (
            RobinhoodOrderExecutionSnapshot(
                broker_order_id=(
                    broker_order_id
                ),
                ref_id=ref_id,
                status=(
                    OrderStatus.FILLED
                ),
                quantity=(
                    self._quantity
                ),
                filled_quantity=(
                    self._quantity
                ),
            )
        )

class ExplodingQuoteProvider:
    def get_quote(
        self,
        symbol: str,
    ):
        raise AssertionError(
            "CLOSING position must not be "
            "monitored as ACTIVE"
        )

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
                        "quantity": None,
                        "cumulative_quantity": "1",
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

    def test_acknowledged_exit_after_crash_blocks_duplicate_exit_until_filled(
        self,
    ) -> None:
        now = datetime(
            2026,
            9,
            26,
            18,
            0,
            tzinfo=timezone.utc,
        )

        account_number = (
            "account-0000"
        )

        position_id = (
            "account-0000:"
            "equity:AAPL:"
            "opening-order-1"
        )

        exit_ref_id = (
            "123e4567-e89b-12d3-a456-426614174001"
        )

        broker_exit_order_id = (
            "broker-exit-order-1"
        )

        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(
                directory
            )

            # -------------------------------------------------
            # Durable position state.
            #
            # This intentionally remains ACTIVE to simulate:
            #
            # broker accepted SELL
            # -> journal ACKNOWLEDGED
            # -> process crashed
            # -> ACTIVE -> CLOSING local sync never happened
            # -------------------------------------------------

            store = (
                SQLitePositionStateStore(
                    directory_path
                    / "positions.sqlite3"
                )
            )

            store.initialize()

            original_state = (
                PositionRuntimeState(
                    position_id=position_id,
                    account_number=(
                        account_number
                    ),
                    asset_type=(
                        AssetType.EQUITY
                    ),
                    symbol="AAPL",
                    opening_order_id=(
                        "opening-order-1"
                    ),
                    entry_price=Decimal(
                        "100"
                    ),
                    remaining_quantity=Decimal(
                        "0.031"
                    ),
                    opened_at=now,
                    highest_executable_bid=Decimal(
                        "110"
                    ),
                    trailing_armed=True,
                    trailing_armed_at=now,
                    activation_gain_ratio=Decimal(
                        "0.04"
                    ),
                    drawdown_ratio=Decimal(
                        "0.02"
                    ),
                    last_quote_at=now,
                    last_reconciled_at=now,
                    status=(
                        PositionStateStatus
                        .ACTIVE
                    ),
                    option_id=None,
                    historical_high_unknown=False,
                    version=3,
                )
            )

            store.insert(
                original_state
            )

            # -------------------------------------------------
            # Durable exit placement journal.
            #
            # Simulate a SELL that Robinhood already accepted.
            # -------------------------------------------------

            journal = (
                SQLitePlacementAttemptJournal(
                    directory_path
                    / "placement.sqlite3"
                )
            )

            journal.initialize()

            request = (
                RobinhoodExitOrderRequest(
                    position_id=position_id,
                    account_number=(
                        account_number
                    ),
                    asset_type=(
                        AssetType.EQUITY
                    ),
                    symbol="AAPL",
                    quantity=Decimal(
                        "0.031"
                    ),
                    action=(
                        RobinhoodExitAction
                        .EQUITY_SELL
                    ),
                    option_id=None,
                )
            )

            submission = (
                RobinhoodExitSubmission(
                    request=request,
                    ref_id=exit_ref_id,
                    order_type=(
                        RobinhoodOrderType
                        .MARKET
                    ),
                )
            )

            journal.insert(
                PlacementAttemptRecord(
                    submission=submission,
                    placement_attempted_at=(
                        now
                    ),
                    status=(
                        PlacementAttemptStatus
                        .PREPARED
                    ),
                )
            )

            journal.transition(
                exit_ref_id,
                expected_status=(
                    PlacementAttemptStatus
                    .PREPARED
                ),
                new_status=(
                    PlacementAttemptStatus
                    .SUBMITTING
                ),
            )

            journal.acknowledge(
                exit_ref_id,
                PlacementAcknowledgement(
                    broker_order_id=(
                        broker_exit_order_id
                    ),
                    acknowledged_at=now,
                ),
            )

            # Sanity check: we have reproduced the
            # exact crash gap.
            before_restart = store.get(
                position_id
            )

            self.assertIsNotNone(
                before_restart
            )

            self.assertEqual(
                before_restart.status,
                PositionStateStatus.ACTIVE,
            )

            resolved = (
                journal.list_resolved()
            )

            self.assertEqual(
                len(resolved),
                1,
            )

            self.assertEqual(
                resolved[0].status,
                PlacementAttemptStatus
                .ACKNOWLEDGED,
            )

            # -------------------------------------------------
            # Simulate process restart.
            #
            # Reconstruct the production reconciliation stack
            # from durable SQLite state only.
            # -------------------------------------------------

            execution_reader = (
                PendingEquityOrderExecutionReader()
            )

            state_reconciler = (
                EquityExitStateReconciler(
                    journal,
                    store,
                )
            )

            close_confirmation_service = (
                EquityPositionCloseConfirmationService(
                    store,
                    execution_reader,
                    clock=lambda: now,
                )
            )

            close_service = (
                JournalBackedEquityPositionCloseService(
                    journal,
                    close_confirmation_service,
                )
            )

            exit_reconciler = (
                RobinhoodEquityExitReconciler(
                    state_reconciler,
                    close_service,
                    store,
                )
            )

            # -------------------------------------------------
            # The old SELL is still pending.
            #
            # Restart reconciliation must:
            #
            # ACTIVE -> CLOSING
            # check the ORIGINAL broker order
            # leave it CLOSING
            # fail closed
            # -------------------------------------------------

            with self.assertRaisesRegex(
                RobinhoodEquityExitReconciliationError,
                (
                    "closing positions "
                    "unresolved"
                ),
            ):
                exit_reconciler.reconcile(
                    account_number=(
                        account_number
                    )
                )

            persisted = store.get(
                position_id
            )

            self.assertIsNotNone(
                persisted
            )

            self.assertEqual(
                persisted.status,
                PositionStateStatus.CLOSING,
            )

            self.assertEqual(
                persisted.version,
                original_state.version + 1,
            )

            # -------------------------------------------------
            # Recovery must follow the original broker order.
            # No new exit provenance may be invented.
            # -------------------------------------------------

            self.assertEqual(
                execution_reader.calls,
                [
                    (
                        account_number,
                        broker_exit_order_id,
                        exit_ref_id,
                    )
                ],
            )

            # -------------------------------------------------
            # Most important duplicate-order invariant:
            #
            # after restart, this position must not appear
            # ACTIVE again.
            # -------------------------------------------------

            active_positions = (
                store.list_by_status(
                    account_number=(
                        account_number
                    ),
                    statuses=(
                        PositionStateStatus
                        .ACTIVE,
                    ),
                )
            )

            self.assertEqual(
                active_positions,
                [],
            )

            closing_positions = (
                store.list_by_status(
                    account_number=(
                        account_number
                    ),
                    statuses=(
                        PositionStateStatus
                        .CLOSING,
                    ),
                )
            )

            self.assertEqual(
                len(closing_positions),
                1,
            )

            self.assertEqual(
                closing_positions[
                    0
                ].position_id,
                position_id,
            )

            # -------------------------------------------------
            # Defense in depth:
            #
            # Even if somebody accidentally invoked the
            # trailing-stop monitor after reconciliation,
            # it sees zero ACTIVE equity positions.
            #
            # Therefore:
            # - no quote read
            # - no new ExitIntent
            # - no second SELL opportunity
            # -------------------------------------------------

            monitor = (
                TrailingStopMonitor(
                    store,
                    ExplodingQuoteProvider(),
                    asset_type_filter=(
                        AssetType.EQUITY
                    ),
                )
            )

            monitor_outcomes = (
                monitor.monitor_active_positions(
                    account_number=(
                        account_number
                    )
                )
            )

            self.assertEqual(
                monitor_outcomes,
                [],
            )

            # Journal must still contain exactly the one
            # original acknowledged SELL.
            resolved_after_restart = (
                journal.list_resolved()
            )

            self.assertEqual(
                len(
                    resolved_after_restart
                ),
                1,
            )

            self.assertEqual(
                resolved_after_restart[
                    0
                ].submission.ref_id,
                exit_ref_id,
            )

    def test_acknowledged_filled_exit_after_crash_converges_to_closed(
        self,
    ) -> None:
        now = datetime(
            2026,
            9,
            26,
            18,
            0,
            tzinfo=timezone.utc,
        )

        account_number = (
            "account-0000"
        )

        quantity = Decimal(
            "0.031"
        )

        position_id = (
            "account-0000:"
            "equity:AAPL:"
            "opening-order-1"
        )

        exit_ref_id = (
            "123e4567-e89b-12d3-a456-426614174002"
        )

        broker_exit_order_id = (
            "broker-exit-order-2"
        )

        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(
                directory
            )

            # -------------------------------------------------
            # Durable local position.
            #
            # Intentionally ACTIVE even though broker already
            # accepted and filled the SELL.
            #
            # This models a crash before local state sync.
            # -------------------------------------------------

            store = (
                SQLitePositionStateStore(
                    directory_path
                    / "positions.sqlite3"
                )
            )

            store.initialize()

            original_state = (
                PositionRuntimeState(
                    position_id=position_id,
                    account_number=(
                        account_number
                    ),
                    asset_type=(
                        AssetType.EQUITY
                    ),
                    symbol="AAPL",
                    opening_order_id=(
                        "opening-order-1"
                    ),
                    entry_price=Decimal(
                        "100"
                    ),
                    remaining_quantity=(
                        quantity
                    ),
                    opened_at=now,
                    highest_executable_bid=Decimal(
                        "110"
                    ),
                    trailing_armed=True,
                    trailing_armed_at=now,
                    activation_gain_ratio=Decimal(
                        "0.04"
                    ),
                    drawdown_ratio=Decimal(
                        "0.02"
                    ),
                    last_quote_at=now,
                    last_reconciled_at=now,
                    status=(
                        PositionStateStatus
                        .ACTIVE
                    ),
                    option_id=None,
                    historical_high_unknown=False,
                    version=3,
                )
            )

            store.insert(
                original_state
            )

            # -------------------------------------------------
            # Durable placement journal.
            #
            # Robinhood already acknowledged the SELL before
            # the process crashed.
            # -------------------------------------------------

            journal = (
                SQLitePlacementAttemptJournal(
                    directory_path
                    / "placement.sqlite3"
                )
            )

            journal.initialize()

            request = (
                RobinhoodExitOrderRequest(
                    position_id=position_id,
                    account_number=(
                        account_number
                    ),
                    asset_type=(
                        AssetType.EQUITY
                    ),
                    symbol="AAPL",
                    quantity=quantity,
                    action=(
                        RobinhoodExitAction
                        .EQUITY_SELL
                    ),
                    option_id=None,
                )
            )

            submission = (
                RobinhoodExitSubmission(
                    request=request,
                    ref_id=exit_ref_id,
                    order_type=(
                        RobinhoodOrderType
                        .MARKET
                    ),
                )
            )

            journal.insert(
                PlacementAttemptRecord(
                    submission=submission,
                    placement_attempted_at=(
                        now
                    ),
                    status=(
                        PlacementAttemptStatus
                        .PREPARED
                    ),
                )
            )

            journal.transition(
                exit_ref_id,
                expected_status=(
                    PlacementAttemptStatus
                    .PREPARED
                ),
                new_status=(
                    PlacementAttemptStatus
                    .SUBMITTING
                ),
            )

            journal.acknowledge(
                exit_ref_id,
                PlacementAcknowledgement(
                    broker_order_id=(
                        broker_exit_order_id
                    ),
                    acknowledged_at=now,
                ),
            )

            # -------------------------------------------------
            # Verify the simulated crash gap.
            # -------------------------------------------------

            before_restart = store.get(
                position_id
            )

            self.assertIsNotNone(
                before_restart
            )

            self.assertEqual(
                before_restart.status,
                PositionStateStatus.ACTIVE,
            )

            self.assertEqual(
                len(
                    journal.list_resolved()
                ),
                1,
            )

            # -------------------------------------------------
            # Restart.
            #
            # Broker reports the ORIGINAL SELL as fully filled.
            # -------------------------------------------------

            execution_reader = (
                FilledEquityOrderExecutionReader(
                    quantity=quantity,
                )
            )

            state_reconciler = (
                EquityExitStateReconciler(
                    journal,
                    store,
                )
            )

            close_confirmation_service = (
                EquityPositionCloseConfirmationService(
                    store,
                    execution_reader,
                    clock=lambda: now,
                )
            )

            close_service = (
                JournalBackedEquityPositionCloseService(
                    journal,
                    close_confirmation_service,
                )
            )

            exit_reconciler = (
                RobinhoodEquityExitReconciler(
                    state_reconciler,
                    close_service,
                    store,
                )
            )

            # -------------------------------------------------
            # Unlike the pending-order crash test, this should
            # complete successfully:
            #
            # ACTIVE
            #   -> repaired to CLOSING
            #   -> original SELL confirmed fully filled
            #   -> CLOSED
            # -------------------------------------------------

            closed_positions = (
                exit_reconciler.reconcile(
                    account_number=(
                        account_number
                    )
                )
            )

            self.assertEqual(
                len(closed_positions),
                1,
            )

            self.assertEqual(
                closed_positions[
                    0
                ].position_id,
                position_id,
            )

            self.assertEqual(
                closed_positions[
                    0
                ].status,
                PositionStateStatus.CLOSED,
            )

            # -------------------------------------------------
            # Durable state must have converged to CLOSED.
            # -------------------------------------------------

            persisted = store.get(
                position_id
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

            # ACTIVE -> CLOSING -> CLOSED
            self.assertEqual(
                persisted.version,
                original_state.version + 2,
            )

            # -------------------------------------------------
            # Must confirm the ORIGINAL broker order.
            #
            # This proves restart reconciliation did not create
            # new exit provenance.
            # -------------------------------------------------

            self.assertEqual(
                execution_reader.calls,
                [
                    (
                        account_number,
                        broker_exit_order_id,
                        exit_ref_id,
                    )
                ],
            )

            # -------------------------------------------------
            # No ACTIVE or CLOSING state remains.
            # -------------------------------------------------

            active_positions = (
                store.list_by_status(
                    account_number=(
                        account_number
                    ),
                    statuses=(
                        PositionStateStatus
                        .ACTIVE,
                    ),
                )
            )

            closing_positions = (
                store.list_by_status(
                    account_number=(
                        account_number
                    ),
                    statuses=(
                        PositionStateStatus
                        .CLOSING,
                    ),
                )
            )

            self.assertEqual(
                active_positions,
                [],
            )

            self.assertEqual(
                closing_positions,
                [],
            )

            # -------------------------------------------------
            # Defense in depth:
            #
            # CLOSED position can never produce another
            # trailing-stop exit.
            # -------------------------------------------------

            monitor = (
                TrailingStopMonitor(
                    store,
                    ExplodingQuoteProvider(),
                    asset_type_filter=(
                        AssetType.EQUITY
                    ),
                )
            )

            monitor_outcomes = (
                monitor.monitor_active_positions(
                    account_number=(
                        account_number
                    )
                )
            )

            self.assertEqual(
                monitor_outcomes,
                [],
            )

            # -------------------------------------------------
            # Still exactly one original SELL provenance.
            # No duplicate placement appeared during recovery.
            # -------------------------------------------------

            resolved_after_restart = (
                journal.list_resolved()
            )

            self.assertEqual(
                len(
                    resolved_after_restart
                ),
                1,
            )

            self.assertEqual(
                resolved_after_restart[
                    0
                ].submission.ref_id,
                exit_ref_id,
            )


if __name__ == "__main__":
    unittest.main()