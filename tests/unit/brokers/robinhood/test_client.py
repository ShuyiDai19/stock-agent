import unittest
from datetime import datetime, timezone

from stock_agent.brokers.robinhood import (
    RobinhoodOrderReceipt,
)


class RobinhoodOrderReceiptTests(unittest.TestCase):
    def test_creates_valid_order_receipt(self) -> None:
        submitted_at = datetime(
            2026,
            8,
            21,
            20,
            0,
            tzinfo=timezone.utc,
        )

        receipt = RobinhoodOrderReceipt(
            broker_order_id="broker-order-123",
            submitted_at=submitted_at,
        )

        self.assertEqual(
            receipt.broker_order_id,
            "broker-order-123",
        )

        self.assertEqual(
            receipt.submitted_at,
            submitted_at,
        )

    def test_rejects_empty_broker_order_id(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "broker_order_id cannot be empty",
        ):
            RobinhoodOrderReceipt(
                broker_order_id=" ",
                submitted_at=datetime.now(
                    timezone.utc
                ),
            )

    def test_rejects_naive_submitted_at(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "submitted_at must be timezone-aware",
        ):
            RobinhoodOrderReceipt(
                broker_order_id="broker-order-123",
                submitted_at=datetime(
                    2026,
                    8,
                    21,
                    20,
                    0,
                ),
            )


if __name__ == "__main__":
    unittest.main()