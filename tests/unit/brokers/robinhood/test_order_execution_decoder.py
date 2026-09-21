import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood.order_execution_decoder import (
    decode_robinhood_filled_order,
)
from stock_agent.domain.enums import (
    OrderStatus,
)


class RobinhoodOrderExecutionDecoderTests(
    unittest.TestCase
):
    BROKER_ORDER_ID = "broker-order-123"

    REF_ID = (
        "00000000-0000-4000-8000-000000000001"
    )

    def make_order(
        self,
        *,
        state: str,
        cumulative_quantity: str = "1",
    ) -> dict:
        return {
            "id": self.BROKER_ORDER_ID,
            "ref_id": self.REF_ID,
            "state": state,
            "quantity": None,
            "cumulative_quantity": (
                cumulative_quantity
            ),
        }

    def test_filled_order_returns_full_fill_snapshot(
        self,
    ) -> None:
        snapshot = decode_robinhood_filled_order(
            self.make_order(
                state="filled"
            ),
            expected_broker_order_id=(
                self.BROKER_ORDER_ID
            ),
            expected_ref_id=self.REF_ID,
        )

        self.assertIsNotNone(
            snapshot
        )

        self.assertEqual(
            snapshot.status,
            OrderStatus.FILLED,
        )

        self.assertEqual(
            snapshot.quantity,
            Decimal("1"),
        )

        self.assertEqual(
            snapshot.filled_quantity,
            Decimal("1"),
        )

        self.assertEqual(
            snapshot.remaining_quantity,
            Decimal("0"),
        )

        self.assertTrue(
            snapshot.confirms_full_fill
        )

    def test_non_filled_states_do_not_confirm_fill(
        self,
    ) -> None:
        for state in (
            "new",
            "queued",
            "confirmed",
            "partially_filled",
            "cancelled",
            "rejected",
            "failed",
            "partially_filled_rest_cancelled",
        ):
            with self.subTest(
                state=state
            ):
                snapshot = (
                    decode_robinhood_filled_order(
                        self.make_order(
                            state=state
                        ),
                        expected_broker_order_id=(
                            self.BROKER_ORDER_ID
                        ),
                        expected_ref_id=(
                            self.REF_ID
                        ),
                    )
                )

                self.assertIsNone(
                    snapshot
                )

    def test_wrong_broker_order_id_is_rejected(
        self,
    ) -> None:
        order = self.make_order(
            state="filled"
        )

        order["id"] = "wrong-order-id"

        with self.assertRaisesRegex(
            ValueError,
            "order id does not match",
        ):
            decode_robinhood_filled_order(
                order,
                expected_broker_order_id=(
                    self.BROKER_ORDER_ID
                ),
                expected_ref_id=self.REF_ID,
            )

    def test_wrong_ref_id_is_rejected(
        self,
    ) -> None:
        order = self.make_order(
            state="filled"
        )

        order["ref_id"] = (
            "00000000-0000-4000-8000-000000000999"
        )

        with self.assertRaisesRegex(
            ValueError,
            "ref_id does not match",
        ):
            decode_robinhood_filled_order(
                order,
                expected_broker_order_id=(
                    self.BROKER_ORDER_ID
                ),
                expected_ref_id=self.REF_ID,
            )

    def test_filled_order_requires_cumulative_quantity(
        self,
    ) -> None:
        order = self.make_order(
            state="filled"
        )

        order.pop(
            "cumulative_quantity"
        )

        with self.assertRaisesRegex(
            ValueError,
            "cumulative_quantity must be a string",
        ):
            decode_robinhood_filled_order(
                order,
                expected_broker_order_id=(
                    self.BROKER_ORDER_ID
                ),
                expected_ref_id=self.REF_ID,
            )

    def test_filled_order_rejects_invalid_cumulative_quantity(
        self,
    ) -> None:
        for cumulative_quantity in (
            "0",
            "-1",
            "nan",
            "not-a-number",
        ):
            with self.subTest(
                cumulative_quantity=(
                    cumulative_quantity
                )
            ):
                with self.assertRaises(
                    ValueError
                ):
                    decode_robinhood_filled_order(
                        self.make_order(
                            state="filled",
                            cumulative_quantity=(
                                cumulative_quantity
                            ),
                        ),
                        expected_broker_order_id=(
                            self.BROKER_ORDER_ID
                        ),
                        expected_ref_id=(
                            self.REF_ID
                        ),
                    )

    def test_decodes_filled_dollar_based_order_using_cumulative_quantity(
        self,
    ) -> None:
        raw_order = {
            "id": "broker-order-1",
            "ref_id": self.REF_ID,
            "state": "filled",
            "quantity": None,
            "cumulative_quantity": (
                "0.040123"
            ),
        }

        snapshot = (
            decode_robinhood_filled_order(
                raw_order,
                expected_broker_order_id=(
                    "broker-order-1"
                ),
                expected_ref_id=self.REF_ID,
            )
        )

        self.assertIsNotNone(
            snapshot
        )

        self.assertEqual(
            snapshot.quantity,
            Decimal("0.040123"),
        )

        self.assertEqual(
            snapshot.filled_quantity,
            Decimal("0.040123"),
        )

        self.assertTrue(
            snapshot.confirms_full_fill
        )


if __name__ == "__main__":
    unittest.main()