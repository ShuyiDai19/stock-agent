import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExitExecutionService,
    ExitIntent,
    ExitReason,
)


class FakeExitExecutor:
    def __init__(
        self,
        *,
        result: ExecutionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.execute_call_count = 0
        self.received_intent = None

    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        self.execute_call_count += 1
        self.received_intent = intent

        if self.error is not None:
            raise self.error

        if self.result is None:
            raise RuntimeError(
                "fake executor result was not configured"
            )

        return self.result


class ExitExecutionServiceTests(unittest.TestCase):
    def make_intent(self) -> ExitIntent:
        return ExitIntent(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime(
                2026,
                8,
                18,
                20,
                0,
                tzinfo=timezone.utc,
            ),
            option_id=None,
        )

    def test_does_not_call_executor_without_exit_intent(
        self,
    ) -> None:
        executor = FakeExitExecutor()
        service = ExitExecutionService(executor)

        result = service.execute(None)

        self.assertIsNone(result)

        self.assertEqual(
            executor.execute_call_count,
            0,
        )

        self.assertIsNone(
            executor.received_intent,
        )

    def test_executes_exit_intent_once(self) -> None:
        intent = self.make_intent()

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

        result = service.execute(intent)

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

    def test_propagates_executor_error(
        self,
    ) -> None:
        intent = self.make_intent()

        executor = FakeExitExecutor(
            error=RuntimeError(
                "broker submission failed"
            ),
        )

        service = ExitExecutionService(executor)

        with self.assertRaisesRegex(
            RuntimeError,
            "broker submission failed",
        ):
            service.execute(intent)

        self.assertEqual(
            executor.execute_call_count,
            1,
        )

        self.assertEqual(
            executor.received_intent,
            intent,
        )


if __name__ == "__main__":
    unittest.main()