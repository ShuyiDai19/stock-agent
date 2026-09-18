import unittest
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import replace

from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExitExecutionService,
    ExitIntent,
    ExitReason,
)
from stock_agent.monitoring import PositionMonitorOutcome
from stock_agent.orchestration import ExitExecutionCoordinator
from stock_agent.risk import (
    TrailingStopDecision,
    TrailingStopEvaluation,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)


class FakeExitExecutor:
    def __init__(
        self,
        *,
        result: ExecutionResult | None = None,
    ) -> None:
        self.result = result
        self.execute_call_count = 0
        self.received_intent = None

    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        self.execute_call_count += 1
        self.received_intent = intent

        if self.result is None:
            raise RuntimeError(
                "fake executor result was not configured"
            )

        return self.result


class FakeBatchExitExecutor:
    def __init__(
        self,
        *,
        results: dict[str, ExecutionResult],
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.results = results
        self.errors = errors or {}

        self.execute_call_count = 0
        self.received_symbols = []

    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        self.execute_call_count += 1
        self.received_symbols.append(
            intent.symbol
        )

        error = self.errors.get(
            intent.symbol
        )

        if error is not None:
            raise error

        result = self.results.get(
            intent.symbol
        )

        if result is None:
            raise RuntimeError(
                f"no execution result configured for {intent.symbol}"
            )

        return result


class FakePositionStateStore:
    def __init__(self) -> None:
        self.states: dict[str, PositionRuntimeState] = {}

    def initialize(self) -> None:
        pass

    def insert(
        self,
        state: PositionRuntimeState,
    ) -> None:
        if state.position_id in self.states:
            raise RuntimeError(
                "position already exists"
            )

        self.states[state.position_id] = state

    def get(
        self,
        position_id: str,
    ) -> PositionRuntimeState | None:
        return self.states.get(
            position_id
        )

    def list_by_status(
        self,
        *,
        account_number: str,
        statuses,
    ) -> list[PositionRuntimeState]:
        return [
            state
            for state in self.states.values()
            if state.account_number == account_number
            and state.status in statuses
        ]

    def update(
        self,
        state: PositionRuntimeState,
        *,
        expected_version: int,
    ) -> None:
        current = self.states.get(
            state.position_id
        )

        if current is None:
            raise RuntimeError(
                "position not found"
            )

        if current.version != expected_version:
            raise RuntimeError(
                "concurrent state update"
            )

        if state.version != expected_version + 1:
            raise ValueError(
                "state.version must equal expected_version + 1"
            )

        self.states[state.position_id] = state


class FailingUpdateStore:
    def __init__(
        self,
        delegate,
    ) -> None:
        self._delegate = delegate

    def get(
        self,
        position_id,
    ):
        return self._delegate.get(
            position_id
        )

    def list_by_status(
        self,
        *,
        account_number,
        statuses,
    ):
        return self._delegate.list_by_status(
            account_number=account_number,
            statuses=statuses,
        )

    def insert(
        self,
        state,
    ) -> None:
        self._delegate.insert(state)

    def initialize(
        self,
    ) -> None:
        self._delegate.initialize()

    def update(
        self,
        state,
        *,
        expected_version,
    ) -> None:
        raise RuntimeError(
            "simulated state persistence failure"
        )


class ExitExecutionCoordinatorTests(unittest.TestCase):
    def make_state(self) -> PositionRuntimeState:
        now = datetime(
            2026,
            8,
            18,
            20,
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
            remaining_quantity=Decimal("0.031"),
            opened_at=now,
            highest_executable_bid=Decimal("110"),
            trailing_armed=True,
            trailing_armed_at=now,
            activation_gain_ratio=Decimal("0.04"),
            drawdown_ratio=Decimal("0.02"),
            last_quote_at=now,
            last_reconciled_at=now,
            status=PositionStateStatus.ACTIVE,
            option_id=None,
            historical_high_unknown=False,
            version=3,
        )

    def make_evaluation(
        self,
        decision: TrailingStopDecision,
    ) -> TrailingStopEvaluation:
        return TrailingStopEvaluation(
            state=self.make_state(),
            decision=decision,
            reason="test evaluation",
        )

    def make_exit_intent(self) -> ExitIntent:
        state = self.make_state()

        return ExitIntent(
            position_id=state.position_id,
            account_number=state.account_number,
            asset_type=state.asset_type,
            symbol=state.symbol,
            quantity=state.remaining_quantity,
            reason=ExitReason.TRAILING_STOP,
            triggered_at=state.last_quote_at,
            option_id=state.option_id,
        )

    def test_does_not_execute_hold_outcome(self) -> None:
        executor = FakeExitExecutor()
        service = ExitExecutionService(executor)
        store = FakePositionStateStore()
        coordinator = ExitExecutionCoordinator(
            service,
            store,
        )

        outcome = PositionMonitorOutcome(
            position_id=self.make_state().position_id,
            symbol="AAPL",
            evaluation=self.make_evaluation(
                TrailingStopDecision.HOLD
            ),
            exit_intent=None,
        )

        result = coordinator.execute_outcome(
            outcome
        )

        self.assertIsNone(result)

        self.assertEqual(
            executor.execute_call_count,
            0,
        )

    def test_does_not_execute_failed_monitor_outcome(
        self,
    ) -> None:
        executor = FakeExitExecutor()
        service = ExitExecutionService(executor)
        store = FakePositionStateStore()
        coordinator = ExitExecutionCoordinator(
            service,
            store,
        )

        outcome = PositionMonitorOutcome(
            position_id=self.make_state().position_id,
            symbol="AAPL",
            error=RuntimeError(
                "quote unavailable"
            ),
        )

        result = coordinator.execute_outcome(
            outcome
        )

        self.assertIsNone(result)

        self.assertEqual(
            executor.execute_call_count,
            0,
        )

    def test_executes_exit_intent_once(self) -> None:
        state = self.make_state()
        intent = self.make_exit_intent()

        execution_result = ExecutionResult(
            position_id=intent.position_id,
            status=ExecutionStatus.SUBMITTED,
            submitted_at=datetime(
                2026,
                8,
                18,
                20,
                1,
                tzinfo=timezone.utc,
            ),
            broker_order_id="broker-order-456",
        )

        executor = FakeExitExecutor(
            result=execution_result,
        )

        service = ExitExecutionService(executor)

        store = FakePositionStateStore()
        store.insert(state)

        coordinator = ExitExecutionCoordinator(
            service,
            store,
        )

        outcome = PositionMonitorOutcome(
            position_id=intent.position_id,
            symbol=intent.symbol,
            evaluation=self.make_evaluation(
                TrailingStopDecision.EXIT
            ),
            exit_intent=intent,
        )

        result = coordinator.execute_outcome(
            outcome
        )

        self.assertEqual(
            executor.execute_call_count,
            1,
        )

        self.assertEqual(
            executor.received_intent,
            intent,
        )

        self.assertEqual(
            result,
            execution_result,
        )

        persisted = store.get(
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

    def test_execute_outcomes_isolates_execution_failures(
        self,
    ) -> None:
        aapl_state = self.make_state()

        msft_state = replace(
            aapl_state,
            position_id="account-0000:equity:MSFT:order-456",
            symbol="MSFT",
            opening_order_id="order-456",
        )

        nvda_state = replace(
            aapl_state,
            position_id="account-0000:equity:NVDA:order-789",
            symbol="NVDA",
            opening_order_id="order-789",
        )

        def make_outcome(
            state: PositionRuntimeState,
        ) -> PositionMonitorOutcome:
            evaluation = TrailingStopEvaluation(
                state=state,
                decision=TrailingStopDecision.EXIT,
                reason="trailing stop triggered",
            )

            intent = ExitIntent(
                position_id=state.position_id,
                account_number=state.account_number,
                asset_type=state.asset_type,
                symbol=state.symbol,
                quantity=state.remaining_quantity,
                reason=ExitReason.TRAILING_STOP,
                triggered_at=state.last_quote_at,
                option_id=state.option_id,
            )

            return PositionMonitorOutcome(
                position_id=state.position_id,
                symbol=state.symbol,
                evaluation=evaluation,
                exit_intent=intent,
            )

        aapl_result = ExecutionResult(
            position_id=aapl_state.position_id,
            status=ExecutionStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            broker_order_id="broker-aapl",
        )

        nvda_result = ExecutionResult(
            position_id=nvda_state.position_id,
            status=ExecutionStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            broker_order_id="broker-nvda",
        )

        executor = FakeBatchExitExecutor(
            results={
                "AAPL": aapl_result,
                "NVDA": nvda_result,
            },
            errors={
                "MSFT": RuntimeError(
                    "MSFT submission failed"
                ),
            },
        )

        service = ExitExecutionService(
            executor
        )

        store = FakePositionStateStore()
        store.insert(aapl_state)
        store.insert(msft_state)
        store.insert(nvda_state)

        coordinator = ExitExecutionCoordinator(
            service,
            store,
        )

        outcomes = coordinator.execute_outcomes(
            [
                make_outcome(aapl_state),
                make_outcome(msft_state),
                make_outcome(nvda_state),
            ]
        )

        self.assertEqual(
            len(outcomes),
            3,
        )

        self.assertEqual(
            executor.received_symbols,
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
            by_symbol["AAPL"].attempted,
        )
        self.assertFalse(
            by_symbol["AAPL"].failed,
        )
        self.assertEqual(
            by_symbol["AAPL"].result,
            aapl_result,
        )

        self.assertTrue(
            by_symbol["MSFT"].attempted,
        )
        self.assertTrue(
            by_symbol["MSFT"].failed,
        )
        self.assertIsInstance(
            by_symbol["MSFT"].error,
            RuntimeError,
        )

        self.assertTrue(
            by_symbol["NVDA"].attempted,
        )
        self.assertFalse(
            by_symbol["NVDA"].failed,
        )
        self.assertEqual(
            by_symbol["NVDA"].result,
            nvda_result,
        )

        self.assertEqual(
            store.get(
                aapl_state.position_id
            ).status,
            PositionStateStatus.CLOSING,
        )

        self.assertEqual(
            store.get(
                msft_state.position_id
            ).status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            store.get(
                nvda_state.position_id
            ).status,
            PositionStateStatus.CLOSING,
        )

    def test_execute_outcomes_marks_hold_as_not_attempted(
        self,
    ) -> None:
        executor = FakeExitExecutor()
        service = ExitExecutionService(
            executor
        )
        store = FakePositionStateStore()

        coordinator = ExitExecutionCoordinator(
            service,
            store,
        )

        state = self.make_state()

        monitor_outcome = PositionMonitorOutcome(
            position_id=state.position_id,
            symbol=state.symbol,
            evaluation=TrailingStopEvaluation(
                state=state,
                decision=TrailingStopDecision.HOLD,
                reason="hold",
            ),
            exit_intent=None,
        )

        outcomes = coordinator.execute_outcomes(
            [monitor_outcome]
        )

        self.assertEqual(
            len(outcomes),
            1,
        )

        self.assertFalse(
            outcomes[0].attempted,
        )

        self.assertIsNone(
            outcomes[0].result,
        )

        self.assertIsNone(
            outcomes[0].error,
        )

        self.assertEqual(
            executor.execute_call_count,
            0,
        )

    def test_submitted_result_is_preserved_when_state_sync_fails(
        self,
    ) -> None:
        state = self.make_state()

        submitted_result = ExecutionResult(
            position_id=state.position_id,
            status=ExecutionStatus.SUBMITTED,
            submitted_at=datetime.now(
                timezone.utc
            ),
            broker_order_id="broker-order-123",
        )

        executor = FakeExitExecutor(
            result=submitted_result
        )

        base_store = FakePositionStateStore()
        base_store.insert(state)

        failing_store = FailingUpdateStore(
            base_store
        )

        coordinator = ExitExecutionCoordinator(
            ExitExecutionService(
                executor
            ),
            failing_store,
        )

        monitor_outcome = PositionMonitorOutcome(
            position_id=state.position_id,
            symbol=state.symbol,
            evaluation=self.make_evaluation(
                TrailingStopDecision.EXIT
            ),
            exit_intent=self.make_exit_intent(),
        )

        outcomes = coordinator.execute_outcomes(
            [monitor_outcome]
        )

        self.assertEqual(
            len(outcomes),
            1,
        )

        outcome = outcomes[0]

        self.assertEqual(
            outcome.result,
            submitted_result,
        )

        self.assertIsNone(
            outcome.error
        )

        self.assertFalse(
            outcome.failed
        )

        self.assertTrue(
            outcome.state_sync_failed
        )

        self.assertIsInstance(
            outcome.state_sync_error,
            RuntimeError,
        )

        persisted = base_store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.ACTIVE,
        )


if __name__ == "__main__":
    unittest.main()