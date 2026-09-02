import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodMCPReceiptDecoder,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType


class RobinhoodMCPReceiptDecoderTests(unittest.TestCase):
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

    def test_decodes_placement_receipt(
        self,
    ) -> None:
        received_at = datetime(
            2026,
            8,
            29,
            6,
            30,
            tzinfo=timezone.utc,
        )

        decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: received_at,
        )

        receipt = decoder(
            self.make_submission(),
            {
                "data": {
                    "order": {
                        "id": "broker-order-123",
                        "symbol": "",
                        "side": "sell",
                        "type": "market",
                        "state": "queued",
                        "quantity": "0.031000",
                        "average_price": None,
                        "last_transaction_at": None,
                        "placed_agent": "agentic",
                        "ref_id": self.REF_ID,
                    }
                }
            },
        )

        self.assertEqual(
            receipt.broker_order_id,
            "broker-order-123",
        )

        self.assertEqual(
            receipt.submitted_at,
            received_at,
        )

    def test_rejects_mismatched_ref_id(
        self,
    ) -> None:
        decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "ref_id does not match submission",
        ):
            decoder(
                self.make_submission(),
                {
                    "data": {
                        "order": {
                            "id": "broker-order-123",
                            "ref_id": (
                                "123e4567-e89b-12d3-a456-426614174999"
                            ),
                        }
                    }
                },
            )

    def test_rejects_missing_order_id(
        self,
    ) -> None:
        decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "must contain order id",
        ):
            decoder(
                self.make_submission(),
                {
                    "data": {
                        "order": {
                            "ref_id": self.REF_ID,
                        }
                    }
                },
            )

    def test_rejects_missing_order(
        self,
    ) -> None:
        decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "must contain order",
        ):
            decoder(
                self.make_submission(),
                {
                    "data": {},
                },
            )

    def test_rejects_missing_data(
        self,
    ) -> None:
        decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: datetime.now(
                timezone.utc
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "must contain data",
        ):
            decoder(
                self.make_submission(),
                {},
            )

    def test_rejects_naive_clock_result(
        self,
    ) -> None:
        decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: datetime(
                2026,
                8,
                29,
                6,
                30,
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "clock must return timezone-aware datetime",
        ):
            decoder(
                self.make_submission(),
                {
                    "data": {
                        "order": {
                            "id": "broker-order-123",
                            "ref_id": self.REF_ID,
                        }
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()