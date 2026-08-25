import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    DryRunRobinhoodExitExecutor,
    LiveRobinhoodExitExecutor,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitPriceQuote,
    RobinhoodExitSubmission,
    RobinhoodMarketHours,
    RobinhoodOrderReceipt,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExecutionStatus,
    ExitIntent,
    ExitReason,
)


class FakeRobinhoodClient:
    def __init__(
        self,
        *,
        receipt: RobinhoodOrderReceipt | None = None,
        error: Exception | None = None,
    ) -> None:
        self.receipt = receipt
        self.error = error

        self.submit_call_count = 0
        self.received_submission = None

    def submit_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReceipt:
        self.submit_call_count += 1
        self.received_submission = submission

        if self.error is not None:
            raise self.error

        if self.receipt is None:
            raise RuntimeError(
                "fake Robinhood receipt was not configured"
            )

        return self.receipt


class FakeRobinhoodExitPriceProvider:
    def __init__(
        self,
        quote: RobinhoodExitPriceQuote,
    ) -> None:
        self.quote = quote
        self.get_exit_price_call_count = 0
        self.received_request = None

    def get_exit_price(
        self,
        request: RobinhoodExitOrderRequest,
    ) -> RobinhoodExitPriceQuote:
        self.get_exit_price_call_count += 1
        self.received_request = request
        return self.quote


class FailingRobinhoodExitPriceProvider:
    def __init__(
        self,
        error: Exception,
    ) -> None:
        self.error = error
        self.get_exit_price_call_count = 0

    def get_exit_price(
        self,
        request: RobinhoodExitOrderRequest,
    ) -> RobinhoodExitPriceQuote:
        self.get_exit_price_call_count += 1
        raise self.error


class RobinhoodExitExecutorTests(unittest.TestCase):
    EQUITY_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    OPTION_REF_ID = (
        "123e4567-e89b-12d3-a456-426614174001"
    )

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

    def test_live_executor_submits_equity_exit_order(
        self,
    ) -> None:
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
                21,
                20,
                0,
                tzinfo=timezone.utc,
            ),
            option_id=None,
        )

        submitted_at = datetime(
            2026,
            8,
            21,
            20,
            1,
            tzinfo=timezone.utc,
        )

        client = FakeRobinhoodClient(
            receipt=RobinhoodOrderReceipt(
                broker_order_id="broker-order-123",
                submitted_at=submitted_at,
            ),
        )

        price_provider = FakeRobinhoodExitPriceProvider(
            RobinhoodExitPriceQuote(
                symbol="AAPL",
                executable_bid=Decimal("107.55"),
                observed_at=datetime(
                    2026,
                    8,
                    21,
                    20,
                    0,
                    30,
                    tzinfo=timezone.utc,
                ),
            )
        )

        executor = LiveRobinhoodExitExecutor(
            client,
            price_provider,
            ref_id_factory=lambda: self.EQUITY_REF_ID,
        )

        result = executor.execute(intent)

        self.assertEqual(
            price_provider.get_exit_price_call_count,
            1,
        )

        self.assertIsNotNone(
            price_provider.received_request,
        )

        self.assertEqual(
            price_provider.received_request.symbol,
            "AAPL",
        )

        self.assertEqual(
            client.submit_call_count,
            1,
        )

        self.assertIsNotNone(
            client.received_submission,
        )

        submission = client.received_submission

        self.assertEqual(
            submission.ref_id,
            self.EQUITY_REF_ID,
        )

        self.assertEqual(
            submission.request.position_id,
            intent.position_id,
        )

        self.assertEqual(
            submission.request.symbol,
            "AAPL",
        )

        self.assertEqual(
            submission.request.quantity,
            Decimal("0.031"),
        )

        self.assertEqual(
            submission.request.action,
            RobinhoodExitAction.EQUITY_SELL,
        )

        self.assertEqual(
            submission.order_type,
            RobinhoodOrderType.MARKET,
        )

        self.assertEqual(
            submission.time_in_force,
            RobinhoodTimeInForce.GFD,
        )

        self.assertEqual(
            submission.market_hours,
            RobinhoodMarketHours.REGULAR_HOURS,
        )

        self.assertIsNone(
            submission.limit_price,
        )

        self.assertEqual(
            result.status,
            ExecutionStatus.SUBMITTED,
        )

        self.assertEqual(
            result.broker_order_id,
            "broker-order-123",
        )

        self.assertEqual(
            result.submitted_at,
            submitted_at,
        )

    def test_live_executor_propagates_client_error(
        self,
    ) -> None:
        intent = ExitIntent(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime.now(
                timezone.utc
            ),
            option_id=None,
        )

        client = FakeRobinhoodClient(
            error=RuntimeError(
                "Robinhood submission failed"
            ),
        )

        price_provider = FakeRobinhoodExitPriceProvider(
            RobinhoodExitPriceQuote(
                symbol="AAPL",
                executable_bid=Decimal("107.55"),
                observed_at=datetime.now(
                    timezone.utc
                ),
            )
        )

        executor = LiveRobinhoodExitExecutor(
            client,
            price_provider,
            ref_id_factory=lambda: self.EQUITY_REF_ID,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Robinhood submission failed",
        ):
            executor.execute(intent)

        self.assertEqual(
            price_provider.get_exit_price_call_count,
            1,
        )

        self.assertEqual(
            client.submit_call_count,
            1,
        )

        self.assertIsNotNone(
            client.received_submission,
        )

        self.assertEqual(
            client.received_submission.ref_id,
            self.EQUITY_REF_ID,
        )

    def test_live_executor_submits_option_sell_to_close(
        self,
    ) -> None:
        intent = ExitIntent(
            position_id="account-0000:option:AAPL:order-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("1"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime.now(
                timezone.utc
            ),
            option_id="option-contract-123",
        )

        client = FakeRobinhoodClient(
            receipt=RobinhoodOrderReceipt(
                broker_order_id="broker-option-456",
                submitted_at=datetime.now(
                    timezone.utc
                ),
            ),
        )

        price_provider = FakeRobinhoodExitPriceProvider(
            RobinhoodExitPriceQuote(
                symbol="AAPL",
                executable_bid=Decimal("2.40"),
                observed_at=datetime.now(
                    timezone.utc
                ),
                option_id="option-contract-123",
            )
        )

        executor = LiveRobinhoodExitExecutor(
            client,
            price_provider,
            ref_id_factory=lambda: self.OPTION_REF_ID,
        )

        result = executor.execute(intent)

        self.assertEqual(
            price_provider.get_exit_price_call_count,
            1,
        )

        self.assertEqual(
            client.submit_call_count,
            1,
        )

        self.assertIsNotNone(
            client.received_submission,
        )

        submission = client.received_submission

        self.assertEqual(
            submission.ref_id,
            self.OPTION_REF_ID,
        )

        self.assertEqual(
            submission.request.action,
            RobinhoodExitAction.OPTION_SELL_TO_CLOSE,
        )

        self.assertEqual(
            submission.request.option_id,
            "option-contract-123",
        )

        self.assertEqual(
            submission.order_type,
            RobinhoodOrderType.LIMIT,
        )

        self.assertEqual(
            submission.limit_price,
            Decimal("2.40"),
        )

        self.assertEqual(
            submission.time_in_force,
            RobinhoodTimeInForce.GFD,
        )

        self.assertEqual(
            submission.market_hours,
            RobinhoodMarketHours.REGULAR_HOURS,
        )

        self.assertEqual(
            result.status,
            ExecutionStatus.SUBMITTED,
        )

    def test_live_executor_does_not_submit_when_pricing_fails(
        self,
    ) -> None:
        intent = ExitIntent(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime.now(
                timezone.utc
            ),
            option_id=None,
        )

        client = FakeRobinhoodClient()

        price_provider = FailingRobinhoodExitPriceProvider(
            RuntimeError(
                "exit quote unavailable"
            )
        )

        executor = LiveRobinhoodExitExecutor(
            client,
            price_provider,
            ref_id_factory=lambda: self.EQUITY_REF_ID,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "exit quote unavailable",
        ):
            executor.execute(intent)

        self.assertEqual(
            price_provider.get_exit_price_call_count,
            1,
        )

        self.assertEqual(
            client.submit_call_count,
            0,
        )

        self.assertIsNone(
            client.received_submission,
        )


if __name__ == "__main__":
    unittest.main()