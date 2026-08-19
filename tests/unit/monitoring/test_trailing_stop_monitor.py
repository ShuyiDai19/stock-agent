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
        states: list[PositionRuntimeState] | None = None,
        error: Exception | None = None,
    ) -> None:
        if state is not None and states is not None:
            raise ValueError(
                "provide either state or states, not both"
            )

        self.state = state
        self.states = states

        self.updated_state = None
        self.updated_states = []

        self.expected_version = None
        self.update_call_count = 0
        self.get_call_count = 0
        self.list_by_status_call_count = 0

        self.requested_position_id = None
        self.requested_account_number = None
        self.requested_statuses = None

        self.error = error

    def get(
        self,
        position_id: str,
    ) -> PositionRuntimeState | None:
        self.get_call_count += 1
        self.requested_position_id = position_id

        if self.states is not None:
            for state in self.states:
                if state.position_id == position_id:
                    return state

            return None

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
        self.updated_states.append(state)
        self.expected_version = expected_version

    def list_by_status(
        self,
        *,
        account_number: str,
        statuses: tuple[PositionStateStatus, ...],
    ) -> list[PositionRuntimeState]:
        self.list_by_status_call_count += 1
        self.requested_account_number = account_number
        self.requested_statuses = statuses

        if self.states is not None:
            candidates = self.states
        elif self.state is not None:
            candidates = [self.state]
        else:
            candidates = []

        return [
            state
            for state in candidates
            if state.account_number == account_number
            and state.status in statuses
        ]


class FakeQuoteProvider:
    def __init__(
        self,
        quote: QuoteSnapshot | None = None,
        *,
        quotes: dict[str, QuoteSnapshot] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.quote = quote
        self.quotes = quotes or {}
        self.errors = errors or {}

        self.requested_symbol = None
        self.requested_symbols = []
        self.get_quote_call_count = 0

    def get_quote(
        self,
        symbol: str,
    ) -> QuoteSnapshot:
        self.get_quote_call_count += 1
        self.requested_symbol = symbol
        self.requested_symbols.append(symbol)

        error = self.errors.get(symbol)

        if error is not None:
            raise error

        quote = self.quotes.get(symbol)

        if quote is not None:
            return quote

        if self.quote is not None:
            return self.quote

        raise RuntimeError(
            f"no quote configured for {symbol}"
        )


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

    def test_monitor_active_positions_processes_active_position(
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

        results = monitor.monitor_active_positions(
            account_number=original.account_number,
        )

        self.assertEqual(
            store.list_by_status_call_count,
            1,
        )

        self.assertEqual(
            store.requested_account_number,
            original.account_number,
        )

        self.assertEqual(
            store.requested_statuses,
            (PositionStateStatus.ACTIVE,),
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertTrue(
            results[0].succeeded,
        )

        self.assertIsNotNone(
            results[0].evaluation,
        )

        self.assertIsNone(
            results[0].exit_intent,
        )

        self.assertEqual(
            results[0].evaluation.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            results[0].evaluation.state.highest_executable_bid,
            Decimal("103"),
        )

        self.assertIsNone(
            results[0].error,
        )

        self.assertEqual(
            quote_provider.get_quote_call_count,
            1,
        )

        self.assertEqual(
            store.update_call_count,
            1,
        )

    def test_monitor_active_positions_isolates_position_failures(
        self,
    ) -> None:
        original = self.make_state()

        msft_state = replace(
            original,
            position_id="account-0000:equity:MSFT:order-456",
            symbol="MSFT",
            opening_order_id="order-456",
        )

        nvda_state = replace(
            original,
            position_id="account-0000:equity:NVDA:order-789",
            symbol="NVDA",
            opening_order_id="order-789",
        )

        observed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        aapl_quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("103"),
            observed_at=observed_at,
        )

        nvda_quote = QuoteSnapshot(
            symbol="NVDA",
            bid=Decimal("103"),
            observed_at=observed_at,
        )

        store = FakePositionStateStore(
            states=[
                original,
                msft_state,
                nvda_state,
            ],
        )

        quote_provider = FakeQuoteProvider(
            quotes={
                "AAPL": aapl_quote,
                "NVDA": nvda_quote,
            },
            errors={
                "MSFT": RuntimeError(
                    "MSFT quote unavailable"
                ),
            },
        )

        monitor = TrailingStopMonitor(
            store,
            quote_provider,
        )

        outcomes = monitor.monitor_active_positions(
            account_number=original.account_number,
        )

        self.assertEqual(
            len(outcomes),
            3,
        )

        self.assertEqual(
            quote_provider.requested_symbols,
            [
                "AAPL",
                "MSFT",
                "NVDA",
            ],
        )

        by_symbol = {
            outcome.symbol: outcome
            for outcome in outcomes
        }

        self.assertTrue(
            by_symbol["AAPL"].succeeded,
        )
        self.assertIsNotNone(
            by_symbol["AAPL"].evaluation,
        )

        self.assertFalse(
            by_symbol["MSFT"].succeeded,
        )
        self.assertIsInstance(
            by_symbol["MSFT"].error,
            RuntimeError,
        )
        self.assertIn(
            "MSFT quote unavailable",
            str(by_symbol["MSFT"].error),
        )

        self.assertIsNone(
            by_symbol["MSFT"].exit_intent,
        )

        self.assertTrue(
            by_symbol["NVDA"].succeeded,
        )
        self.assertIsNotNone(
            by_symbol["NVDA"].evaluation,
        )

        # AAPL and NVDA were persisted.
        # MSFT failed before evaluation/persistence.
        self.assertEqual(
            store.update_call_count,
            2,
        )

        self.assertEqual(
            [
                state.symbol
                for state in store.updated_states
            ],
            [
                "AAPL",
                "NVDA",
            ],
        )

    def test_monitor_active_positions_builds_exit_intent_for_exit(
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

        outcomes = monitor.monitor_active_positions(
            account_number=armed_state.account_number,
        )

        self.assertEqual(
            len(outcomes),
            1,
        )

        outcome = outcomes[0]

        self.assertTrue(
            outcome.succeeded,
        )

        self.assertIsNotNone(
            outcome.evaluation,
        )

        self.assertEqual(
            outcome.evaluation.decision,
            TrailingStopDecision.EXIT,
        )

        self.assertIsNotNone(
            outcome.exit_intent,
        )

        self.assertEqual(
            outcome.exit_intent.position_id,
            armed_state.position_id,
        )

        self.assertEqual(
            outcome.exit_intent.symbol,
            "AAPL",
        )

        self.assertEqual(
            outcome.exit_intent.quantity,
            armed_state.remaining_quantity,
        )

        self.assertEqual(
            outcome.exit_intent.triggered_at,
            outcome.evaluation.state.last_quote_at,
        )


if __name__ == "__main__":
    unittest.main()