import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    GuardedRobinhoodBrokerClient,
    LiveExecutionDisabledError,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderReceipt,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType


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
                "fake receipt was not configured"
            )

        return self.receipt


class GuardedRobinhoodBrokerClientTests(unittest.TestCase):
    REF_ID = "123e4567-e89b-12d3-a456-426614174000"

    def make_request(
        self,
    ) -> RobinhoodExitOrderRequest:
        return RobinhoodExitOrderRequest(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

    def make_submission(
        self,
    ) -> RobinhoodExitSubmission:
        return RobinhoodExitSubmission(
            request=self.make_request(),
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

    def test_blocks_submission_when_live_execution_disabled(
        self,
    ) -> None:
        delegate = FakeRobinhoodClient()

        client = GuardedRobinhoodBrokerClient(
            delegate,
            live_enabled=False,
        )

        with self.assertRaisesRegex(
            LiveExecutionDisabledError,
            "live Robinhood execution is disabled",
        ):
            client.submit_exit_order(
                self.make_submission()
            )

        self.assertEqual(
            delegate.submit_call_count,
            0,
        )

        self.assertIsNone(
            delegate.received_submission,
        )

    def test_forwards_submission_when_live_execution_enabled(
        self,
    ) -> None:
        submission = self.make_submission()

        receipt = RobinhoodOrderReceipt(
            broker_order_id="broker-order-123",
            submitted_at=datetime(
                2026,
                8,
                21,
                22,
                0,
                tzinfo=timezone.utc,
            ),
        )

        delegate = FakeRobinhoodClient(
            receipt=receipt,
        )

        client = GuardedRobinhoodBrokerClient(
            delegate,
            live_enabled=True,
        )

        result = client.submit_exit_order(
            submission
        )

        self.assertEqual(
            delegate.submit_call_count,
            1,
        )

        self.assertEqual(
            delegate.received_submission,
            submission,
        )

        self.assertEqual(
            delegate.received_submission.ref_id,
            self.REF_ID,
        )

        self.assertEqual(
            result,
            receipt,
        )

    def test_propagates_delegate_error_when_enabled(
        self,
    ) -> None:
        delegate = FakeRobinhoodClient(
            error=RuntimeError(
                "broker submission failed"
            ),
        )

        client = GuardedRobinhoodBrokerClient(
            delegate,
            live_enabled=True,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "broker submission failed",
        ):
            client.submit_exit_order(
                self.make_submission()
            )

        self.assertEqual(
            delegate.submit_call_count,
            1,
        )

        self.assertIsNotNone(
            delegate.received_submission,
        )

    def test_rejects_non_boolean_live_enabled(
        self,
    ) -> None:
        delegate = FakeRobinhoodClient()

        with self.assertRaisesRegex(
            TypeError,
            "live_enabled must be a bool",
        ):
            GuardedRobinhoodBrokerClient(
                delegate,
                live_enabled="false",  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()