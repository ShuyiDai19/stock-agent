import unittest
from decimal import Decimal
from typing import Any

from stock_agent.brokers.robinhood.mcp_order_execution_reader import (
    MCPRobinhoodEquityOrderExecutionReader,
)
from stock_agent.domain.enums import (
    OrderStatus,
)


class FakeMCPToolInvoker:
    def __init__(
        self,
        result: Any,
    ) -> None:
        self.result = result
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append(
            (
                tool_name,
                arguments,
            )
        )

        return self.result


class MCPRobinhoodEquityOrderExecutionReaderTests(
    unittest.TestCase
):
    ACCOUNT_NUMBER = "agentic-account"

    BROKER_ORDER_ID = "broker-order-123"

    REF_ID = (
        "00000000-0000-4000-8000-000000000001"
    )

    def make_order(
        self,
        *,
        state: str,
        quantity: str = "1",
    ) -> dict[str, Any]:
        return {
            "id": self.BROKER_ORDER_ID,
            "ref_id": self.REF_ID,
            "state": state,
            "quantity": quantity,
        }

    def test_reads_filled_equity_order(
        self,
    ) -> None:
        invoker = FakeMCPToolInvoker(
            {
                "data": {
                    "orders": [
                        self.make_order(
                            state="filled"
                        )
                    ]
                }
            }
        )

        reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        snapshot = reader.read(
            account_number=self.ACCOUNT_NUMBER,
            broker_order_id=(
                self.BROKER_ORDER_ID
            ),
            ref_id=self.REF_ID,
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_equity_orders",
                    {
                        "account_number": (
                            self.ACCOUNT_NUMBER
                        ),
                        "order_id": (
                            self.BROKER_ORDER_ID
                        ),
                    },
                )
            ],
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

        self.assertTrue(
            snapshot.confirms_full_fill
        )

    def test_non_filled_order_returns_none(
        self,
    ) -> None:
        invoker = FakeMCPToolInvoker(
            {
                "data": {
                    "orders": [
                        self.make_order(
                            state="queued"
                        )
                    ]
                }
            }
        )

        reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        snapshot = reader.read(
            account_number=self.ACCOUNT_NUMBER,
            broker_order_id=(
                self.BROKER_ORDER_ID
            ),
            ref_id=self.REF_ID,
        )

        self.assertIsNone(
            snapshot
        )

    def test_empty_order_result_returns_none(
        self,
    ) -> None:
        invoker = FakeMCPToolInvoker(
            {
                "data": {
                    "orders": []
                }
            }
        )

        reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        snapshot = reader.read(
            account_number=self.ACCOUNT_NUMBER,
            broker_order_id=(
                self.BROKER_ORDER_ID
            ),
            ref_id=self.REF_ID,
        )

        self.assertIsNone(
            snapshot
        )

    def test_multiple_orders_are_rejected(
        self,
    ) -> None:
        order = self.make_order(
            state="filled"
        )

        invoker = FakeMCPToolInvoker(
            {
                "data": {
                    "orders": [
                        order,
                        dict(order),
                    ]
                }
            }
        )

        reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "at most one order",
        ):
            reader.read(
                account_number=(
                    self.ACCOUNT_NUMBER
                ),
                broker_order_id=(
                    self.BROKER_ORDER_ID
                ),
                ref_id=self.REF_ID,
            )

    def test_wrong_order_identity_is_rejected(
        self,
    ) -> None:
        order = self.make_order(
            state="filled"
        )

        order["ref_id"] = (
            "00000000-0000-4000-8000-000000000999"
        )

        invoker = FakeMCPToolInvoker(
            {
                "data": {
                    "orders": [
                        order
                    ]
                }
            }
        )

        reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "ref_id does not match",
        ):
            reader.read(
                account_number=(
                    self.ACCOUNT_NUMBER
                ),
                broker_order_id=(
                    self.BROKER_ORDER_ID
                ),
                ref_id=self.REF_ID,
            )

    def test_malformed_result_is_rejected(
        self,
    ) -> None:
        invoker = FakeMCPToolInvoker(
            {
                "data": {}
            }
        )

        reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "must contain orders",
        ):
            reader.read(
                account_number=(
                    self.ACCOUNT_NUMBER
                ),
                broker_order_id=(
                    self.BROKER_ORDER_ID
                ),
                ref_id=self.REF_ID,
            )


if __name__ == "__main__":
    unittest.main()