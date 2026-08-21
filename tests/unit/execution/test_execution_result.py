import unittest
from datetime import datetime, timezone

from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)


class ExecutionResultTests(unittest.TestCase):
    def test_creates_submitted_execution_result(self) -> None:
        submitted_at = datetime(
            2026,
            8,
            18,
            2,
            30,
            tzinfo=timezone.utc,
        )

        result = ExecutionResult(
            position_id="account-0000:equity:AAPL:order-123",
            status=ExecutionStatus.SUBMITTED,
            submitted_at=submitted_at,
            broker_order_id="broker-order-456",
        )

        self.assertEqual(
            result.status,
            ExecutionStatus.SUBMITTED,
        )

        self.assertEqual(
            result.broker_order_id,
            "broker-order-456",
        )

        self.assertEqual(
            result.submitted_at,
            submitted_at,
        )

    def test_creates_rejected_execution_result(self) -> None:
        result = ExecutionResult(
            position_id="account-0000:equity:AAPL:order-123",
            status=ExecutionStatus.REJECTED,
            submitted_at=datetime.now(timezone.utc),
            message="order rejected",
        )

        self.assertEqual(
            result.status,
            ExecutionStatus.REJECTED,
        )

        self.assertIsNone(
            result.broker_order_id,
        )

        self.assertEqual(
            result.message,
            "order rejected",
        )

    def test_rejects_empty_position_id(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "position_id cannot be empty",
        ):
            ExecutionResult(
                position_id=" ",
                status=ExecutionStatus.REJECTED,
                submitted_at=datetime.now(timezone.utc),
            )

    def test_submitted_result_requires_broker_order_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "submitted execution must have broker_order_id",
        ):
            ExecutionResult(
                position_id="position-123",
                status=ExecutionStatus.SUBMITTED,
                submitted_at=datetime.now(timezone.utc),
                broker_order_id=None,
            )

    def test_rejects_naive_submitted_at(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "submitted_at must be timezone-aware",
        ):
            ExecutionResult(
                position_id="position-123",
                status=ExecutionStatus.REJECTED,
                submitted_at=datetime(
                    2026,
                    8,
                    18,
                    2,
                    30,
                ),
            )

    def test_creates_previewed_execution_result(self) -> None:
        result = ExecutionResult(
            position_id="account-0000:equity:AAPL:order-123",
            status=ExecutionStatus.PREVIEWED,
            submitted_at=datetime.now(timezone.utc),
            message="dry-run order preview",
        )

        self.assertEqual(
            result.status,
            ExecutionStatus.PREVIEWED,
        )

        self.assertIsNone(
            result.broker_order_id,
        )

        self.assertEqual(
            result.message,
            "dry-run order preview",
        )


if __name__ == "__main__":
    unittest.main()