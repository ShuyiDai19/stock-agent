import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.domain.enums import (
    OrderStatus,
)


class RobinhoodOrderExecutionSnapshotTests(
    unittest.TestCase
):
    def test_filled_order_confirms_full_fill(
        self,
    ) -> None:
        snapshot = RobinhoodOrderExecutionSnapshot(
            broker_order_id="broker-order-1",
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
            status=OrderStatus.FILLED,
            quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
        )

        self.assertTrue(
            snapshot.confirms_full_fill
        )

        self.assertEqual(
            snapshot.remaining_quantity,
            Decimal("0"),
        )

    def test_partial_fill_does_not_confirm_full_fill(
        self,
    ) -> None:
        snapshot = RobinhoodOrderExecutionSnapshot(
            broker_order_id="broker-order-1",
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
            status=OrderStatus.PARTIALLY_FILLED,
            quantity=Decimal("1"),
            filled_quantity=Decimal("0.4"),
        )

        self.assertFalse(
            snapshot.confirms_full_fill
        )

        self.assertEqual(
            snapshot.remaining_quantity,
            Decimal("0.6"),
        )

    def test_filled_status_requires_full_quantity(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "filled order must have",
        ):
            RobinhoodOrderExecutionSnapshot(
                broker_order_id="broker-order-1",
                ref_id=(
                    "00000000-0000-4000-8000-000000000001"
                ),
                status=OrderStatus.FILLED,
                quantity=Decimal("1"),
                filled_quantity=Decimal("0.4"),
            )

    def test_partial_fill_requires_strictly_partial_quantity(
        self,
    ) -> None:
        for filled_quantity in (
            Decimal("0"),
            Decimal("1"),
        ):
            with self.subTest(
                filled_quantity=filled_quantity
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "partially filled order must have",
                ):
                    RobinhoodOrderExecutionSnapshot(
                        broker_order_id=(
                            "broker-order-1"
                        ),
                        ref_id=(
                            "00000000-0000-4000-8000-000000000001"
                        ),
                        status=(
                            OrderStatus
                            .PARTIALLY_FILLED
                        ),
                        quantity=Decimal("1"),
                        filled_quantity=(
                            filled_quantity
                        ),
                    )

    def test_cancelled_order_does_not_confirm_full_fill(
        self,
    ) -> None:
        snapshot = RobinhoodOrderExecutionSnapshot(
            broker_order_id="broker-order-1",
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
            status=OrderStatus.CANCELLED,
            quantity=Decimal("1"),
            filled_quantity=Decimal("0.4"),
        )

        self.assertFalse(
            snapshot.confirms_full_fill
        )

        self.assertEqual(
            snapshot.remaining_quantity,
            Decimal("0.6"),
        )


if __name__ == "__main__":
    unittest.main()