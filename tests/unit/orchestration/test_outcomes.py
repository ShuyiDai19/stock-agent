import unittest
from datetime import datetime, timezone

from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from stock_agent.orchestration.outcomes import (
    PositionExecutionOutcome,
)


_NOW = datetime(
    2026,
    9,
    18,
    tzinfo=timezone.utc,
)


def make_submitted_result() -> ExecutionResult:
    return ExecutionResult(
        position_id="position-1",
        status=ExecutionStatus.SUBMITTED,
        submitted_at=_NOW,
        broker_order_id="broker-order-1",
    )


class PositionExecutionOutcomeTests(
    unittest.TestCase
):
    def test_submitted_result_can_include_state_sync_error(
        self,
    ) -> None:
        error = RuntimeError(
            "state persistence failed"
        )

        outcome = PositionExecutionOutcome(
            position_id="position-1",
            symbol="AAPL",
            result=make_submitted_result(),
            state_sync_error=error,
        )

        self.assertTrue(
            outcome.attempted
        )

        self.assertFalse(
            outcome.failed
        )

        self.assertTrue(
            outcome.state_sync_failed
        )

        self.assertIs(
            outcome.state_sync_error,
            error,
        )

    def test_result_and_execution_error_are_mutually_exclusive(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "both result and error",
        ):
            PositionExecutionOutcome(
                position_id="position-1",
                symbol="AAPL",
                result=make_submitted_result(),
                error=RuntimeError(
                    "submission failed"
                ),
            )

    def test_state_sync_error_requires_result(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "requires an execution result",
        ):
            PositionExecutionOutcome(
                position_id="position-1",
                symbol="AAPL",
                state_sync_error=RuntimeError(
                    "state persistence failed"
                ),
            )

    def test_state_sync_error_requires_submitted_result(
        self,
    ) -> None:
        previewed = ExecutionResult(
            position_id="position-1",
            status=ExecutionStatus.PREVIEWED,
            submitted_at=_NOW,
        )

        with self.assertRaisesRegex(
            ValueError,
            "submitted execution result",
        ):
            PositionExecutionOutcome(
                position_id="position-1",
                symbol="AAPL",
                result=previewed,
                state_sync_error=RuntimeError(
                    "state persistence failed"
                ),
            )

    def test_execution_error_remains_failed(
        self,
    ) -> None:
        outcome = PositionExecutionOutcome(
            position_id="position-1",
            symbol="AAPL",
            error=RuntimeError(
                "submission failed"
            ),
        )

        self.assertTrue(
            outcome.attempted
        )

        self.assertTrue(
            outcome.failed
        )

        self.assertFalse(
            outcome.state_sync_failed
        )