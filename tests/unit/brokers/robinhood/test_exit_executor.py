import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    DryRunRobinhoodExitExecutor,
    RobinhoodExitAction,
)
from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionStatus,
    ExitIntent,
    ExitReason,
)


class DryRunRobinhoodExitExecutorTests(unittest.TestCase):
    def test_previews_equity_sell_without_submitting_order(
        self,
    ) -> None:
        previewed_at = datetime(
            2026,
            8,
            19,
            3,
            0,
            tzinfo=timezone.utc,
        )

        intent = ExitIntent(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime(
                2026,
                8,
                19,
                2,
                59,
                tzinfo=timezone.utc,
            ),
            option_id=None,
        )

        executor = DryRunRobinhoodExitExecutor(
            clock=lambda: previewed_at,
        )

        result = executor.execute(intent)

        self.assertEqual(
            result.status,
            ExecutionStatus.PREVIEWED,
        )

        self.assertIsNone(
            result.broker_order_id,
        )

        self.assertEqual(
            result.position_id,
            intent.position_id,
        )

        self.assertEqual(
            result.submitted_at,
            previewed_at,
        )

        self.assertIsNotNone(
            executor.last_request,
        )

        request = executor.last_request

        self.assertEqual(
            request.action,
            RobinhoodExitAction.EQUITY_SELL,
        )

        self.assertEqual(
            request.symbol,
            "AAPL",
        )

        self.assertEqual(
            request.quantity,
            Decimal("0.031"),
        )

        self.assertIsNone(
            request.option_id,
        )

    def test_previews_option_sell_to_close_without_submitting_order(
        self,
    ) -> None:
        intent = ExitIntent(
            position_id="account-0000:option:AAPL:order-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("1"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime(
                2026,
                8,
                19,
                3,
                0,
                tzinfo=timezone.utc,
            ),
            option_id="option-contract-123",
        )

        executor = DryRunRobinhoodExitExecutor(
            clock=lambda: datetime(
                2026,
                8,
                19,
                3,
                1,
                tzinfo=timezone.utc,
            ),
        )

        result = executor.execute(intent)

        self.assertEqual(
            result.status,
            ExecutionStatus.PREVIEWED,
        )

        self.assertIsNone(
            result.broker_order_id,
        )

        self.assertIsNotNone(
            executor.last_request,
        )

        request = executor.last_request

        self.assertEqual(
            request.action,
            RobinhoodExitAction.OPTION_SELL_TO_CLOSE,
        )

        self.assertEqual(
            request.quantity,
            Decimal("1"),
        )

        self.assertEqual(
            request.option_id,
            "option-contract-123",
        )

    def test_rejects_option_exit_without_option_id(
        self,
    ) -> None:
        intent = ExitIntent(
            position_id="account-0000:option:AAPL:order-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("1"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime.now(timezone.utc),
            option_id=None,
        )

        executor = DryRunRobinhoodExitExecutor()

        with self.assertRaisesRegex(
            ValueError,
            "option exit intent requires option_id",
        ):
            executor.execute(intent)

        self.assertIsNone(
            executor.last_request,
        )

    def test_rejects_fractional_option_exit_quantity(
        self,
    ) -> None:
        intent = ExitIntent(
            position_id="account-0000:option:AAPL:order-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("0.5"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime.now(timezone.utc),
            option_id="option-contract-123",
        )

        executor = DryRunRobinhoodExitExecutor()

        with self.assertRaisesRegex(
            ValueError,
            "option exit quantity must be whole contracts",
        ):
            executor.execute(intent)

        self.assertIsNone(
            executor.last_request,
        )


if __name__ == "__main__":
    unittest.main()