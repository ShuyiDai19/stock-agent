import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from stock_agent.brokers.robinhood.exit_state_reconciliation import (
    EquityExitStateReconciliationError,
    EquityExitStateReconciler,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAcknowledgement,
    PlacementAttemptRecord,
    PlacementAttemptStatus,
    PlacementRecoveryEvidence,
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
    23,
    13,
    0,
    tzinfo=timezone.utc,
)


class FakeResolvedPlacementJournal:
    def __init__(
        self,
        records,
    ) -> None:
        self._records = list(records)

    def list_resolved(
        self,
    ):
        return list(
            self._records
        )


class EquityExitStateReconciliationTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        self.store = (
            SQLitePositionStateStore(
                Path(
                    self.temp_directory.name
                )
                / "positions.sqlite3"
            )
        )
        self.store.initialize()

    def tearDown(
        self,
    ) -> None:
        self.temp_directory.cleanup()

    def make_state(
        self,
        *,
        account_number: str = (
            "account-0000"
        ),
        symbol: str = "AAPL",
        quantity: Decimal = Decimal(
            "0.031"
        ),
    ) -> PositionRuntimeState:
        return PositionRuntimeState(
            position_id=(
                f"{account_number}:"
                f"equity:{symbol}:order-123"
            ),
            account_number=account_number,
            asset_type=AssetType.EQUITY,
            symbol=symbol,
            opening_order_id="order-123",
            entry_price=Decimal("100"),
            remaining_quantity=quantity,
            opened_at=_NOW,
            highest_executable_bid=(
                Decimal("110")
            ),
            trailing_armed=True,
            trailing_armed_at=_NOW,
            activation_gain_ratio=(
                Decimal("0.04")
            ),
            drawdown_ratio=(
                Decimal("0.02")
            ),
            last_quote_at=_NOW,
            last_reconciled_at=_NOW,
            status=(
                PositionStateStatus.ACTIVE
            ),
            option_id=None,
            historical_high_unknown=False,
            version=3,
        )

    def make_record(
        self,
        state: PositionRuntimeState,
        *,
        ref_id: str = (
            "123e4567-e89b-12d3-a456-426614174001"
        ),
        status: PlacementAttemptStatus = (
            PlacementAttemptStatus
            .ACKNOWLEDGED
        ),
        account_number: str | None = None,
        symbol: str | None = None,
        quantity: Decimal | None = None,
        broker_order_id: str = (
            "broker-exit-1"
        ),
    ) -> PlacementAttemptRecord:
        request = RobinhoodExitOrderRequest(
            position_id=state.position_id,
            account_number=(
                state.account_number
                if account_number is None
                else account_number
            ),
            asset_type=AssetType.EQUITY,
            symbol=(
                state.symbol
                if symbol is None
                else symbol
            ),
            quantity=(
                state.remaining_quantity
                if quantity is None
                else quantity
            ),
            action=(
                RobinhoodExitAction
                .EQUITY_SELL
            ),
            option_id=None,
        )

        submission = (
            RobinhoodExitSubmission(
                request=request,
                ref_id=ref_id,
                order_type=(
                    RobinhoodOrderType
                    .MARKET
                ),
            )
        )

        acknowledgement = None
        recovery_evidence = None

        if (
            status
            is PlacementAttemptStatus
            .ACKNOWLEDGED
        ):
            acknowledgement = (
                PlacementAcknowledgement(
                    broker_order_id=(
                        broker_order_id
                    ),
                    acknowledged_at=_NOW,
                )
            )

        elif (
            status
            is PlacementAttemptStatus
            .RECOVERED
        ):
            recovery_evidence = (
                PlacementRecoveryEvidence(
                    broker_order_id=(
                        broker_order_id
                    ),
                    recovered_at=_NOW,
                )
            )

        return PlacementAttemptRecord(
            submission=submission,
            placement_attempted_at=_NOW,
            status=status,
            acknowledgement=acknowledgement,
            recovery_evidence=(
                recovery_evidence
            ),
        )

    def test_acknowledged_exit_repairs_active_position_to_closing(
        self,
    ) -> None:
        state = self.make_state()
        self.store.insert(
            state
        )

        record = self.make_record(
            state,
            status=(
                PlacementAttemptStatus
                .ACKNOWLEDGED
            ),
        )

        reconciler = (
            EquityExitStateReconciler(
                FakeResolvedPlacementJournal(
                    [record]
                ),
                self.store,
            )
        )

        results = reconciler.reconcile(
            account_number=(
                state.account_number
            )
        )

        self.assertEqual(
            len(results),
            1,
        )
        self.assertTrue(
            results[0].repaired
        )

        persisted = self.store.get(
            state.position_id
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
            state.version + 1,
        )

    def test_recovered_exit_repairs_active_position_to_closing(
        self,
    ) -> None:
        state = self.make_state()
        self.store.insert(
            state
        )

        record = self.make_record(
            state,
            status=(
                PlacementAttemptStatus
                .RECOVERED
            ),
            broker_order_id=(
                "broker-recovered-exit-1"
            ),
        )

        reconciler = (
            EquityExitStateReconciler(
                FakeResolvedPlacementJournal(
                    [record]
                ),
                self.store,
            )
        )

        results = reconciler.reconcile(
            account_number=(
                state.account_number
            )
        )

        self.assertEqual(
            len(results),
            1,
        )
        self.assertTrue(
            results[0].repaired
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertIsNotNone(
            persisted
        )
        self.assertEqual(
            persisted.status,
            PositionStateStatus.CLOSING,
        )

    def test_active_position_without_resolved_exit_remains_active(
        self,
    ) -> None:
        state = self.make_state()
        self.store.insert(
            state
        )

        reconciler = (
            EquityExitStateReconciler(
                FakeResolvedPlacementJournal(
                    []
                ),
                self.store,
            )
        )

        results = reconciler.reconcile(
            account_number=(
                state.account_number
            )
        )

        self.assertEqual(
            len(results),
            1,
        )
        self.assertFalse(
            results[0].repaired
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
            persisted.version,
            state.version,
        )

    def test_mismatched_closing_provenance_fails_closed(
        self,
    ) -> None:
        cases = (
            (
                "account",
                {
                    "account_number":
                        "different-account",
                },
                "account",
            ),
            (
                "symbol",
                {
                    "symbol": "MSFT",
                },
                "symbol",
            ),
            (
                "quantity",
                {
                    "quantity":
                        Decimal("0.030"),
                },
                "quantity",
            ),
        )

        for (
            label,
            record_overrides,
            expected_message,
        ) in cases:
            with self.subTest(
                case=label
            ):
                with tempfile.TemporaryDirectory() as directory:
                    store = (
                        SQLitePositionStateStore(
                            Path(directory)
                            / "positions.sqlite3"
                        )
                    )
                    store.initialize()

                    state = self.make_state()
                    store.insert(
                        state
                    )

                    record = self.make_record(
                        state,
                        **record_overrides,
                    )

                    reconciler = (
                        EquityExitStateReconciler(
                            FakeResolvedPlacementJournal(
                                [record]
                            ),
                            store,
                        )
                    )

                    with self.assertRaisesRegex(
                        EquityExitStateReconciliationError,
                        expected_message,
                    ):
                        reconciler.reconcile(
                            account_number=(
                                state.account_number
                            )
                        )

                    persisted = store.get(
                        state.position_id
                    )

                    self.assertIsNotNone(
                        persisted
                    )
                    self.assertEqual(
                        persisted.status,
                        PositionStateStatus.ACTIVE,
                    )

    def test_malformed_non_sell_equity_provenance_fails_closed(
        self,
    ) -> None:
        state = self.make_state()
        self.store.insert(
            state
        )

        malformed_record = (
            SimpleNamespace(
                submission=SimpleNamespace(
                    request=SimpleNamespace(
                        position_id=(
                            state.position_id
                        ),
                        account_number=(
                            state.account_number
                        ),
                        asset_type=(
                            AssetType.EQUITY
                        ),
                        symbol=state.symbol,
                        quantity=(
                            state
                            .remaining_quantity
                        ),
                        action=(
                            RobinhoodExitAction
                            .OPTION_SELL_TO_CLOSE
                        ),
                    )
                ),
                status=(
                    PlacementAttemptStatus
                    .ACKNOWLEDGED
                ),
                acknowledgement=(
                    PlacementAcknowledgement(
                        broker_order_id=(
                            "broker-exit-1"
                        ),
                        acknowledged_at=(
                            _NOW
                        ),
                    )
                ),
                recovery_evidence=None,
            )
        )

        reconciler = (
            EquityExitStateReconciler(
                FakeResolvedPlacementJournal(
                    [malformed_record]
                ),
                self.store,
            )
        )

        with self.assertRaisesRegex(
            EquityExitStateReconciliationError,
            "equity sell",
        ):
            reconciler.reconcile(
                account_number=(
                    state.account_number
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

    def test_multiple_resolved_exits_for_active_position_fail_closed(
        self,
    ) -> None:
        state = self.make_state()
        self.store.insert(
            state
        )

        first = self.make_record(
            state,
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174001"
            ),
            broker_order_id=(
                "broker-exit-1"
            ),
        )

        second = self.make_record(
            state,
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174002"
            ),
            broker_order_id=(
                "broker-exit-2"
            ),
        )

        reconciler = (
            EquityExitStateReconciler(
                FakeResolvedPlacementJournal(
                    [
                        first,
                        second,
                    ]
                ),
                self.store,
            )
        )

        with self.assertRaisesRegex(
            EquityExitStateReconciliationError,
            "multiple resolved",
        ):
            reconciler.reconcile(
                account_number=(
                    state.account_number
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

    def test_repaired_exit_is_not_visible_as_active_again(
        self,
    ) -> None:
        state = self.make_state()
        self.store.insert(
            state
        )

        record = self.make_record(
            state
        )

        reconciler = (
            EquityExitStateReconciler(
                FakeResolvedPlacementJournal(
                    [record]
                ),
                self.store,
            )
        )

        reconciler.reconcile(
            account_number=(
                state.account_number
            )
        )

        active = (
            self.store.list_by_status(
                account_number=(
                    state.account_number
                ),
                statuses=(
                    PositionStateStatus
                    .ACTIVE,
                ),
            )
        )

        closing = (
            self.store.list_by_status(
                account_number=(
                    state.account_number
                ),
                statuses=(
                    PositionStateStatus
                    .CLOSING,
                ),
            )
        )

        self.assertEqual(
            active,
            [],
        )
        self.assertEqual(
            len(closing),
            1,
        )
        self.assertEqual(
            closing[0].position_id,
            state.position_id,
        )


if __name__ == "__main__":
    unittest.main()
