import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitPriceQuote,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
    build_robinhood_exit_submission,
)
from stock_agent.domain import AssetType


class RobinhoodExitPricingTests(unittest.TestCase):
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

    def test_builds_limit_submission_from_executable_bid(
        self,
    ) -> None:
        request = self.make_equity_request()

        quote = RobinhoodExitPriceQuote(
            symbol="AAPL",
            executable_bid=Decimal("107.80"),
            observed_at=datetime(
                2026,
                8,
                21,
                23,
                40,
                tzinfo=timezone.utc,
            ),
        )

        submission = build_robinhood_exit_submission(
            request,
            quote,
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

    def test_rejects_quote_symbol_mismatch(
        self,
    ) -> None:
        request = self.make_equity_request()

        quote = RobinhoodExitPriceQuote(
            symbol="MSFT",
            executable_bid=Decimal("107.80"),
            observed_at=datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "quote symbol does not match request symbol",
        ):
            build_robinhood_exit_submission(
                request,
                quote,
            )

    def test_requires_matching_option_contract(
        self,
    ) -> None:
        request = RobinhoodExitOrderRequest(
            position_id="account-0000:option:AAPL:order-456",
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("1"),
            action=RobinhoodExitAction.OPTION_SELL_TO_CLOSE,
            option_id="option-contract-123",
        )

        quote = RobinhoodExitPriceQuote(
            symbol="AAPL",
            executable_bid=Decimal("2.40"),
            observed_at=datetime.now(
                timezone.utc
            ),
            option_id="option-contract-999",
        )

        with self.assertRaisesRegex(
            ValueError,
            "quote option_id does not match request option_id",
        ):
            build_robinhood_exit_submission(
                request,
                quote,
            )

    def test_rejects_non_positive_executable_bid(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "executable_bid must be greater than zero",
        ):
            RobinhoodExitPriceQuote(
                symbol="AAPL",
                executable_bid=Decimal("0"),
                observed_at=datetime.now(
                    timezone.utc
                ),
            )

    def test_rejects_non_finite_executable_bid(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "executable_bid must be finite",
        ):
            RobinhoodExitPriceQuote(
                symbol="AAPL",
                executable_bid=Decimal("NaN"),
                observed_at=datetime.now(
                    timezone.utc
                ),
            )

    def test_rejects_naive_observed_at(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "observed_at must be timezone-aware",
        ):
            RobinhoodExitPriceQuote(
                symbol="AAPL",
                executable_bid=Decimal("107.80"),
                observed_at=datetime(
                    2026,
                    8,
                    21,
                    23,
                    40,
                ),
            )


if __name__ == "__main__":
    unittest.main()