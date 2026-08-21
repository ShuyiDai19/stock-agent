import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.domain import AssetType


class RobinhoodExitSubmissionTests(unittest.TestCase):
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

    def test_creates_limit_gfd_submission(
        self,
    ) -> None:
        request = self.make_request()

        submission = RobinhoodExitSubmission(
            request=request,
            limit_price=Decimal("107.80"),
        )

        self.assertEqual(
            submission.request,
            request,
        )

        self.assertEqual(
            submission.limit_price,
            Decimal("107.80"),
        )

        self.assertEqual(
            submission.order_type,
            RobinhoodOrderType.LIMIT,
        )

        self.assertEqual(
            submission.time_in_force,
            RobinhoodTimeInForce.GFD,
        )

    def test_rejects_zero_limit_price(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "limit_price must be greater than zero",
        ):
            RobinhoodExitSubmission(
                request=self.make_request(),
                limit_price=Decimal("0"),
            )

    def test_rejects_negative_limit_price(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "limit_price must be greater than zero",
        ):
            RobinhoodExitSubmission(
                request=self.make_request(),
                limit_price=Decimal("-1"),
            )

    def test_rejects_non_finite_limit_price(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "limit_price must be finite",
        ):
            RobinhoodExitSubmission(
                request=self.make_request(),
                limit_price=Decimal("NaN"),
            )


if __name__ == "__main__":
    unittest.main()