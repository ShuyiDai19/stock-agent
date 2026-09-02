import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
    build_robinhood_mcp_review_call,
    build_robinhood_mcp_place_call,
)
from stock_agent.domain import AssetType


class RobinhoodMCPMappingTests(unittest.TestCase):
    REF_ID = "123e4567-e89b-12d3-a456-426614174000"

    def test_maps_fractional_equity_exit_to_review_call(
        self,
    ) -> None:
        request = RobinhoodExitOrderRequest(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

        call = build_robinhood_mcp_review_call(
            submission
        )

        self.assertEqual(
            call.tool_name,
            "review_equity_order",
        )

        self.assertEqual(
            call.arguments,
            {
                "account_number": "account-0000",
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
            },
        )

        self.assertNotIn(
            "ref_id",
            call.arguments,
        )

    def test_maps_option_exit_to_sell_to_close_review_call(
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

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.LIMIT,
            limit_price=Decimal("2.40"),
        )

        call = build_robinhood_mcp_review_call(
            submission
        )

        self.assertEqual(
            call.tool_name,
            "review_option_order",
        )

        self.assertEqual(
            call.arguments,
            {
                "account_number": "account-0000",
                "legs": [
                    {
                        "option_id": "option-contract-123",
                        "side": "sell",
                        "position_effect": "close",
                        "ratio_quantity": 1,
                    }
                ],
                "type": "limit",
                "quantity": "1",
                "price": "2.40",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
                "chain_symbol": "AAPL",
                "underlying_type": "equity",
            },
        )

        self.assertNotIn(
            "ref_id",
            call.arguments,
        )

    def test_rejects_market_option_exit(
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

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

        with self.assertRaisesRegex(
            ValueError,
            "option exit submission must use limit order",
        ):
            build_robinhood_mcp_review_call(
                submission
            )

        with self.assertRaisesRegex(
            ValueError,
            "option exit submission must use limit order",
        ):
            build_robinhood_mcp_place_call(
                submission
            )

    def test_maps_fractional_equity_exit_to_place_call(
        self,
    ) -> None:
        request = RobinhoodExitOrderRequest(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

        call = build_robinhood_mcp_place_call(
            submission
        )

        self.assertEqual(
            call.tool_name,
            "place_equity_order",
        )

        self.assertEqual(
            call.arguments,
            {
                "account_number": "account-0000",
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
                "ref_id": self.REF_ID,
            },
        )

    def test_maps_option_exit_to_sell_to_close_place_call(
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

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.LIMIT,
            limit_price=Decimal("2.40"),
        )

        call = build_robinhood_mcp_place_call(
            submission
        )

        self.assertEqual(
            call.tool_name,
            "place_option_order",
        )

        self.assertEqual(
            call.arguments,
            {
                "account_number": "account-0000",
                "legs": [
                    {
                        "option_id": "option-contract-123",
                        "side": "sell",
                        "position_effect": "close",
                        "ratio_quantity": 1,
                    }
                ],
                "type": "limit",
                "quantity": "1",
                "price": "2.40",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
                "ref_id": self.REF_ID,
            },
        )

        self.assertNotIn(
            "chain_symbol",
            call.arguments,
        )

        self.assertNotIn(
            "underlying_type",
            call.arguments,
        )

    def test_option_review_and_place_use_same_order_parameters(
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

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.LIMIT,
            limit_price=Decimal("2.40"),
        )

        review_call = build_robinhood_mcp_review_call(
            submission
        )

        place_call = build_robinhood_mcp_place_call(
            submission
        )

        review_arguments = dict(
            review_call.arguments
        )

        review_arguments.pop(
            "chain_symbol"
        )

        review_arguments.pop(
            "underlying_type"
        )

        place_arguments = dict(
            place_call.arguments
        )

        place_arguments.pop(
            "ref_id"
        )

        self.assertEqual(
            place_arguments,
            review_arguments,
        )

if __name__ == "__main__":
    unittest.main()