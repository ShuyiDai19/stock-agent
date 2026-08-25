import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodMarketHours,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.domain import AssetType


class RobinhoodExitSubmissionTests(unittest.TestCase):
    def make_equity_request(
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

    def make_option_request(
        self,
    ) -> RobinhoodExitOrderRequest:
        return RobinhoodExitOrderRequest(
            position_id="account-0000:option:AAPL:order-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("1"),
            action=RobinhoodExitAction.OPTION_SELL_TO_CLOSE,
            option_id="option-contract-123",
        )

    def test_creates_limit_gfd_submission(
        self,
    ) -> None:
        request = self.make_option_request()

        submission = RobinhoodExitSubmission(
            request=request,
            order_type=RobinhoodOrderType.LIMIT,
            limit_price=Decimal("2.40"),
        )

        self.assertEqual(
            submission.request,
            request,
        )

        self.assertEqual(
            submission.limit_price,
            Decimal("2.40"),
        )

        self.assertEqual(
            submission.order_type,
            RobinhoodOrderType.LIMIT,
        )

        self.assertEqual(
            submission.time_in_force,
            RobinhoodTimeInForce.GFD,
        )

        self.assertEqual(
            submission.market_hours,
            RobinhoodMarketHours.REGULAR_HOURS,
        )

    def test_creates_market_regular_hours_submission(
        self,
    ) -> None:
        request = self.make_equity_request()

        submission = RobinhoodExitSubmission(
            request=request,
            order_type=RobinhoodOrderType.MARKET,
        )

        self.assertEqual(
            submission.request,
            request,
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

    def test_limit_order_requires_limit_price(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "limit order requires limit_price",
        ):
            RobinhoodExitSubmission(
                request=self.make_option_request(),
                order_type=RobinhoodOrderType.LIMIT,
            )

    def test_rejects_limit_price_on_market_order(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "market order cannot contain limit_price",
        ):
            RobinhoodExitSubmission(
                request=self.make_equity_request(),
                order_type=RobinhoodOrderType.MARKET,
                limit_price=Decimal("107.80"),
            )

    def test_rejects_zero_limit_price(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "limit_price must be greater than zero",
        ):
            RobinhoodExitSubmission(
                request=self.make_option_request(),
                order_type=RobinhoodOrderType.LIMIT,
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
                request=self.make_option_request(),
                order_type=RobinhoodOrderType.LIMIT,
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
                request=self.make_option_request(),
                order_type=RobinhoodOrderType.LIMIT,
                limit_price=Decimal("NaN"),
            )


if __name__ == "__main__":
    unittest.main()