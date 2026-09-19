import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import Any

from stock_agent.brokers.robinhood.entry_fill import (
    confirm_and_activate_equity_entry,
    decode_confirmed_equity_entry_fill,
)
from stock_agent.domain import (
    QuoteSnapshot,
)
from stock_agent.state import (
    PositionStateStatus,
)


_FILLED_AT = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)

_REF_ID = (
    "123e4567-e89b-12d3-a456-426614174000"
)


def filled_order(
    *,
    state: str = "filled",
    ref_id: str = _REF_ID,
    average_price: str | None = "199.40",
) -> dict:
    return {
        "data": {
            "orders": [
                {
                    "id": "broker-order-1",
                    "ref_id": ref_id,
                    "symbol": "AAPL",
                    "side": "buy",
                    "type": "market",
                    "state": state,

                    # Dollar-based orders may not
                    # have request quantity.
                    "quantity": None,

                    "cumulative_quantity": (
                        "0.040123"
                    ),
                    "average_price": (
                        average_price
                    ),
                    "last_transaction_at": (
                        _FILLED_AT
                        .isoformat()
                        .replace(
                            "+00:00",
                            "Z",
                        )
                    ),
                }
            ]
        }
    }


class FakeInvoker:
    def __init__(
        self,
        result: Any,
    ) -> None:
        self.result = result
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        return self.result


class FakeQuoteProvider:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def get_quote(
        self,
        symbol,
    ):
        self.calls.append(
            symbol
        )

        return QuoteSnapshot(
            symbol=symbol,
            bid=Decimal("199.35"),
            observed_at=(
                _FILLED_AT
                + timedelta(
                    seconds=1
                )
            ),
        )


class FakeStore:
    def __init__(
        self,
    ) -> None:
        self.states = {}
        self.insert_call_count = 0

    def get(
        self,
        position_id,
    ):
        return self.states.get(
            position_id
        )

    def insert(
        self,
        state,
    ) -> None:
        self.insert_call_count += 1
        self.states[
            state.position_id
        ] = state


class EntryFillTests(
    unittest.TestCase
):
    def test_decodes_fractional_filled_order(
        self,
    ) -> None:
        fill = (
            decode_confirmed_equity_entry_fill(
                filled_order(),
                account_number=(
                    "agentic-account"
                ),
                symbol="AAPL",
                broker_order_id=(
                    "broker-order-1"
                ),
                ref_id=_REF_ID,
            )
        )

        self.assertIsNotNone(
            fill
        )

        self.assertEqual(
            fill.filled_quantity,
            Decimal("0.040123"),
        )

        self.assertEqual(
            fill.average_fill_price,
            Decimal("199.40"),
        )

        self.assertEqual(
            fill.filled_at,
            _FILLED_AT,
        )

    def test_nonfilled_order_does_not_activate(
        self,
    ) -> None:
        invoker = FakeInvoker(
            filled_order(
                state="confirmed"
            )
        )

        quote_provider = (
            FakeQuoteProvider()
        )

        store = FakeStore()

        result = (
            confirm_and_activate_equity_entry(
                invoker,
                store,
                quote_provider,
                account_number=(
                    "agentic-account"
                ),
                symbol="AAPL",
                broker_order_id=(
                    "broker-order-1"
                ),
                ref_id=_REF_ID,
            )
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            quote_provider.calls,
            [],
        )

        self.assertEqual(
            store.insert_call_count,
            0,
        )

    def test_filled_order_activates_position(
        self,
    ) -> None:
        invoker = FakeInvoker(
            filled_order()
        )

        quote_provider = (
            FakeQuoteProvider()
        )

        store = FakeStore()

        state = (
            confirm_and_activate_equity_entry(
                invoker,
                store,
                quote_provider,
                account_number=(
                    "agentic-account"
                ),
                symbol="AAPL",
                broker_order_id=(
                    "broker-order-1"
                ),
                ref_id=_REF_ID,
            )
        )

        self.assertIsNotNone(
            state
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_equity_orders",
                    {
                        "account_number": (
                            "agentic-account"
                        ),
                        "order_id": (
                            "broker-order-1"
                        ),
                    },
                )
            ],
        )

        self.assertEqual(
            state.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            state.entry_price,
            Decimal("199.40"),
        )

        self.assertEqual(
            state.remaining_quantity,
            Decimal("0.040123"),
        )

        self.assertEqual(
            quote_provider.calls,
            ["AAPL"],
        )

        self.assertEqual(
            store.insert_call_count,
            1,
        )

    def test_rejects_wrong_ref_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ref_id does not match",
        ):
            decode_confirmed_equity_entry_fill(
                filled_order(
                    ref_id="wrong-ref-id"
                ),
                account_number=(
                    "agentic-account"
                ),
                symbol="AAPL",
                broker_order_id=(
                    "broker-order-1"
                ),
                ref_id=_REF_ID,
            )

    def test_rejects_filled_order_without_average_price(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "average_price is missing",
        ):
            decode_confirmed_equity_entry_fill(
                filled_order(
                    average_price=None
                ),
                account_number=(
                    "agentic-account"
                ),
                symbol="AAPL",
                broker_order_id=(
                    "broker-order-1"
                ),
                ref_id=_REF_ID,
            )


if __name__ == "__main__":
    unittest.main()