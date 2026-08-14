import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stock_agent.domain import (
    AssetType,
    QuoteSnapshot,
)
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


class FakeQuoteProvider:
    def __init__(
        self,
        quote: QuoteSnapshot,
    ) -> None:
        self.quote = quote
        self.requested_symbol = None
        self.get_quote_call_count = 0

    def get_quote(
        self,
        symbol: str,
    ) -> QuoteSnapshot:
        self.get_quote_call_count += 1
        self.requested_symbol = symbol
        return self.quote


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

    def test_process_position_reads_quote_and_persists_evaluated_state(
        self,
    ) -> None:
        original = self.make_state()

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("103"),
            observed_at=(
                original.last_quote_at
                + timedelta(minutes=5)
            ),
        )

        store = FakePositionStateStore(
            state=original,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        result = monitor.process_position(
            original.position_id,
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
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("103"),
        )

        self.assertEqual(
            result.state.version,
            2,
        )

        self.assertEqual(
            store.updated_state,
            result.state,
        )

        self.assertEqual(
            store.expected_version,
            1,
        )

    def test_process_position_persists_exit_without_closing_position(
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

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("107.80"),
            observed_at=(
                armed_at
                + timedelta(minutes=5)
            ),
        )

        store = FakePositionStateStore(
            state=armed_state,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        result = monitor.process_position(
            armed_state.position_id,
        )

        self.assertEqual(
            store.get_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.EXIT,
        )

        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            store.updated_state,
            result.state,
        )

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

    def test_process_position_propagates_concurrent_update_error(
        self,
    ) -> None:
        original = self.make_state()

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("103"),
            observed_at=(
                original.last_quote_at
                + timedelta(minutes=5)
            ),
        )

        store = FakePositionStateStore(
            state=original,
            error=ConcurrentStateUpdateError(
                "position state version conflict"
            ),
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        with self.assertRaisesRegex(
            ConcurrentStateUpdateError,
            "version conflict",
        ):
            monitor.process_position(
                original.position_id,
            )

        self.assertEqual(
            store.get_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            store.update_call_count,
            1,
        )

    def test_process_position_does_not_persist_inactive_position(
        self,
    ) -> None:
        original = self.make_state()

        closed_state = replace(
            original,
            status=PositionStateStatus.CLOSED,
            remaining_quantity=Decimal("0"),
        )

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("101"),
            observed_at=(
                closed_state.last_quote_at
                + timedelta(minutes=5)
            ),
        )

        store = FakePositionStateStore(
            state=closed_state,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        with self.assertRaisesRegex(
            ValueError,
            "active position",
        ):
            monitor.process_position(
                closed_state.position_id,
            )

        self.assertEqual(
            store.get_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )

    def test_process_position_raises_when_position_is_missing(
        self,
    ) -> None:
        position_id = "account-0000:equity:AAPL:missing-order"

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("103"),
            observed_at=datetime(
                2026,
                8,
                1,
                14,
                5,
                tzinfo=timezone.utc,
            ),
        )

        store = FakePositionStateStore(
            state=None,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        with self.assertRaisesRegex(
            PositionStateNotFoundError,
            "position state not found",
        ):
            monitor.process_position(
                position_id,
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
            quote_provider.get_quote_call_count,
            0,
        )

        self.assertIsNone(
            quote_provider.requested_symbol,
        )

        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )

    def test_process_position_does_not_persist_stale_quote(
        self,
    ) -> None:
        original = self.make_state()

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("105"),
            observed_at=(
                original.last_quote_at
                - timedelta(minutes=1)
            ),
        )

        store = FakePositionStateStore(
            state=original,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        with self.assertRaisesRegex(
            ValueError,
            "observed_at cannot be earlier than last_quote_at",
        ):
            monitor.process_position(
                original.position_id,
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
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )

    def test_process_position_does_not_persist_same_timestamp_quote(
        self,
    ) -> None:
        original = self.make_state()

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("105"),
            observed_at=original.last_quote_at,
        )

        store = FakePositionStateStore(
            state=original,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        with self.assertRaisesRegex(
            ValueError,
            "observed_at must be later than last_quote_at",
        ):
            monitor.process_position(
                original.position_id,
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
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )

    def test_process_position_rejects_symbol_mismatch(
        self,
    ) -> None:
        original = self.make_state()

        quote = QuoteSnapshot(
            symbol="MSFT",
            bid=Decimal("103"),
            observed_at=(
                original.last_quote_at
                + timedelta(minutes=5)
            ),
        )

        store = FakePositionStateStore(
            state=original,
        )

        quote_provider = FakeQuoteProvider(
            quote=quote,
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        with self.assertRaisesRegex(
            ValueError,
            "quote symbol does not match position symbol",
        ):
            monitor.process_position(
                original.position_id,
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
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            quote_provider.requested_symbol,
            "AAPL",
        )

        self.assertEqual(
            store.update_call_count,
            0,
        )

        self.assertIsNone(
            store.updated_state,
        )


if __name__ == "__main__":
    unittest.main()