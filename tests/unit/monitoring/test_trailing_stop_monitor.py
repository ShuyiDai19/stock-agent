import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.monitoring import TrailingStopMonitor
from stock_agent.risk import TrailingStopDecision
from stock_agent.state import (
    ConcurrentStateUpdateError,
    PositionRuntimeState,
    PositionStateNotFoundError,
    PositionStateStatus,
)


class FakePositionStateStore:
    def __init__(
        self,
        *,
        state: PositionRuntimeState | None = None,
        error: Exception | None = None,
    ) -> None:
        self.state = state
        self.updated_state = None
        self.expected_version = None
        self.update_call_count = 0
        self.get_call_count = 0
        self.requested_position_id = None
        self.error = error

    def get(
        self,
        position_id: str,
    ) -> PositionRuntimeState | None:
        self.get_call_count += 1
        self.requested_position_id = position_id
        return self.state

    def update(
        self,
        state: PositionRuntimeState,
        *,
        expected_version: int,
    ) -> None:
        self.update_call_count += 1

        if self.error is not None:
            raise self.error

        self.updated_state = state
        self.expected_version = expected_version


class TrailingStopMonitorTests(unittest.TestCase):
    def make_state(self) -> PositionRuntimeState:
        opened_at = datetime(
            2026,
            8,
            1,
            14,
            0,
            tzinfo=timezone.utc,
        )

        return PositionRuntimeState(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            opening_order_id="order-123",
            entry_price=Decimal("100"),
            remaining_quantity=Decimal("1"),
            opened_at=opened_at,
            highest_executable_bid=Decimal("100"),
            trailing_armed=False,
            trailing_armed_at=None,
            activation_gain_ratio=Decimal("0.04"),
            drawdown_ratio=Decimal("0.02"),
            last_quote_at=opened_at,
            last_reconciled_at=opened_at,
            status=PositionStateStatus.ACTIVE,
            option_id=None,
            historical_high_unknown=False,
            version=1,
        )

    def test_process_quote_reads_and_persists_evaluated_state(
        self,
    ) -> None:
        original = self.make_state()

        store = FakePositionStateStore(
            state=original,
        )
        monitor = TrailingStopMonitor(store)

        observed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        result = monitor.process_quote(
            original.position_id,
            latest_bid=Decimal("103"),
            observed_at=observed_at,
        )

        self.assertEqual(
            store.get_call_count,
            1,
        )
        self.assertEqual(
            store.requested_position_id,
            original.position_id,
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            store.updated_state,
            result.state,
        )

        self.assertEqual(
            store.expected_version,
            1,
        )

        self.assertEqual(
            result.state.version,
            2,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("103"),
        )

    def test_process_quote_persists_exit_without_closing_position(
        self,
    ) -> None:
        original = self.make_state()

        armed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        armed_state = replace(
            original,
            highest_executable_bid=Decimal("110"),
            trailing_armed=True,
            trailing_armed_at=armed_at,
            last_quote_at=armed_at,
            version=2,
        )

        store = FakePositionStateStore(
            state=armed_state,
        )
        monitor = TrailingStopMonitor(store)

        observed_at = (
            armed_at
            + timedelta(minutes=5)
        )

        result = monitor.process_quote(
            armed_state.position_id,
            latest_bid=Decimal("107.80"),
            observed_at=observed_at,
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.EXIT,
        )

        # EXIT is only a risk decision.
        # The position remains active until execution succeeds.
        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

        # The evaluated runtime state is still persisted.
        self.assertEqual(
            store.updated_state,
            result.state,
        )

        # Optimistic concurrency uses the state version
        # that was read before evaluation.
        self.assertEqual(
            store.expected_version,
            2,
        )

        self.assertEqual(
            result.state.version,
            3,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("110"),
        )

    def test_process_quote_propagates_concurrent_update_error(
        self,
    ) -> None:
        original = self.make_state()

        store = FakePositionStateStore(
            state=original,
            error=ConcurrentStateUpdateError(
                "position state version conflict"
            ),
        )
        monitor = TrailingStopMonitor(store)

        observed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        with self.assertRaisesRegex(
            ConcurrentStateUpdateError,
            "version conflict",
        ):
            monitor.process_quote(
                original.position_id,
                latest_bid=Decimal("103"),
                observed_at=observed_at,
            )

        self.assertEqual(
            store.get_call_count,
            1,
        )
        self.assertEqual(
            store.update_call_count,
            1,
        )

    def test_process_quote_does_not_persist_when_bid_is_invalid(
        self,
    ) -> None:
        original = self.make_state()

        store = FakePositionStateStore(
            state=original,
        )
        monitor = TrailingStopMonitor(store)

        observed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        with self.assertRaisesRegex(
            ValueError,
            "latest_bid must be greater than zero",
        ):
            monitor.process_quote(
                original.position_id,
                latest_bid=Decimal("0"),
                observed_at=observed_at,
            )

        self.assertEqual(
            store.get_call_count,
            1,
        )
        self.assertEqual(
            store.update_call_count,
            0,
        )
        self.assertIsNone(
            store.updated_state,
        )

    def test_process_quote_does_not_persist_inactive_position(
        self,
    ) -> None:
        original = self.make_state()

        closed_state = replace(
            original,
            status=PositionStateStatus.CLOSED,
            remaining_quantity=Decimal("0"),
        )

        store = FakePositionStateStore(
            state=closed_state,
        )
        monitor = TrailingStopMonitor(store)

        observed_at = (
            closed_state.last_quote_at
            + timedelta(minutes=5)
        )

        with self.assertRaisesRegex(
            ValueError,
            "active position",
        ):
            monitor.process_quote(
                closed_state.position_id,
                latest_bid=Decimal("101"),
                observed_at=observed_at,
            )

        self.assertEqual(
            store.get_call_count,
            1,
        )
        self.assertEqual(
            store.update_call_count,
            0,
        )
        self.assertIsNone(
            store.updated_state,
        )

    def test_process_quote_raises_when_position_is_missing(
        self,
    ) -> None:
        store = FakePositionStateStore(
            state=None,
        )
        monitor = TrailingStopMonitor(store)

        position_id = "account-0000:equity:AAPL:missing-order"

        observed_at = datetime(
            2026,
            8,
            1,
            14,
            5,
            tzinfo=timezone.utc,
        )

        with self.assertRaisesRegex(
            PositionStateNotFoundError,
            "position state not found",
        ):
            monitor.process_quote(
                position_id,
                latest_bid=Decimal("103"),
                observed_at=observed_at,
            )

        self.assertEqual(
            store.get_call_count,
            1,
        )

        self.assertEqual(
            store.requested_position_id,
            position_id,
        )

        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )

    def test_process_quote_does_not_persist_stale_quote(
        self,
    ) -> None:
        original = self.make_state()

        store = FakePositionStateStore(
            state=original,
        )
        monitor = TrailingStopMonitor(store)

        stale_observed_at = (
            original.last_quote_at
            - timedelta(minutes=1)
        )

        with self.assertRaisesRegex(
            ValueError,
            "observed_at cannot be earlier than last_quote_at",
        ):
            monitor.process_quote(
                original.position_id,
                latest_bid=Decimal("105"),
                observed_at=stale_observed_at,
            )

        # The monitor must read the latest persisted state first.
        self.assertEqual(
            store.get_call_count,
            1,
        )

        self.assertEqual(
            store.requested_position_id,
            original.position_id,
        )

        # Evaluation failed, so persistence must never happen.
        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )

    def test_process_quote_does_not_persist_same_timestamp_quote(
        self,
    ) -> None:
        original = self.make_state()

        store = FakePositionStateStore(
            state=original,
        )
        monitor = TrailingStopMonitor(store)

        with self.assertRaisesRegex(
            ValueError,
            "observed_at must be later than last_quote_at",
        ):
            monitor.process_quote(
                original.position_id,
                latest_bid=Decimal("105"),
                observed_at=original.last_quote_at,
            )

        # Monitor must read the latest state first.
        self.assertEqual(
            store.get_call_count,
            1,
        )

        self.assertEqual(
            store.requested_position_id,
            original.position_id,
        )

        # Rejected duplicate/ambiguous quote must never be persisted.
        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )


if __name__ == "__main__":
    unittest.main()