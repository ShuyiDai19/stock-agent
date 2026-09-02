import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderReview,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType


class RobinhoodOrderReviewTests(unittest.TestCase):
    REF_ID = "123e4567-e89b-12d3-a456-426614174000"

    def make_submission(
        self,
    ) -> RobinhoodExitSubmission:
        request = RobinhoodExitOrderRequest(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

        return RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

    def test_creates_approved_review(
        self,
    ) -> None:
        submission = self.make_submission()

        review = RobinhoodOrderReview(
            submission=submission,
            approved=True,
        )

        self.assertTrue(
            review.approved,
        )

        self.assertEqual(
            review.submission,
            submission,
        )

        self.assertEqual(
            review.alerts,
            (),
        )

    def test_creates_rejected_review_with_alerts(
        self,
    ) -> None:
        submission = self.make_submission()

        review = RobinhoodOrderReview(
            submission=submission,
            approved=False,
            alerts=(
                "insufficient buying power",
                "order not permitted",
            ),
        )

        self.assertFalse(
            review.approved,
        )

        self.assertEqual(
            review.alerts,
            (
                "insufficient buying power",
                "order not permitted",
            ),
        )

    def test_rejects_empty_alert(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "review alerts cannot contain empty values",
        ):
            RobinhoodOrderReview(
                submission=self.make_submission(),
                approved=False,
                alerts=(" ",),
            )


if __name__ == "__main__":
    unittest.main()