import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
    decode_robinhood_mcp_review,
)
from stock_agent.domain import AssetType


class RobinhoodMCPReviewDecoderTests(unittest.TestCase):
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

    def test_approves_review_with_empty_order_checks(
        self,
    ) -> None:
        submission = self.make_submission()

        raw_result = {
            "data": {
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "order_checks": {},
                "quote_data": {
                    "bid_price": "316.94",
                    "ask_price": "320.26",
                },
                "market_data_disclosure": (
                    "fake disclosure"
                ),
            }
        }

        review = decode_robinhood_mcp_review(
            submission,
            raw_result,
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

    def test_rejects_review_with_order_checks(
        self,
    ) -> None:
        submission = self.make_submission()

        raw_result = {
            "data": {
                "order_checks": {
                    "example_check": {
                        "detail": "order not permitted"
                    }
                }
            }
        }

        review = decode_robinhood_mcp_review(
            submission,
            raw_result,
        )

        self.assertFalse(
            review.approved,
        )

        self.assertEqual(
            len(review.alerts),
            1,
        )

        self.assertIn(
            "order not permitted",
            review.alerts[0],
        )

    def test_rejects_missing_data(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must contain data",
        ):
            decode_robinhood_mcp_review(
                self.make_submission(),
                {},
            )

    def test_rejects_missing_order_checks(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must contain order_checks",
        ):
            decode_robinhood_mcp_review(
                self.make_submission(),
                {
                    "data": {
                        "symbol": "AAPL",
                    }
                },
            )

    def test_rejects_non_mapping_result(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must be a mapping",
        ):
            decode_robinhood_mcp_review(
                self.make_submission(),
                "invalid",
            )


if __name__ == "__main__":
    unittest.main()