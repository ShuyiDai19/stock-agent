import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp_entry_funds_reader import (
    MCPRobinhoodEntryFundsReader,
    decode_robinhood_entry_funds,
)


def portfolio_payload(
    *,
    cash="90.75",
    buying_power="999.00",
    unleveraged_buying_power="90.7500",
    currency="USD",
    display_currency="USD",
):
    return {
        "data": {
            "cash": cash,
            "currency": currency,
            "buying_power": {
                "buying_power":
                    buying_power,
                "unleveraged_buying_power":
                    unleveraged_buying_power,
                "display_currency":
                    display_currency,
            },
        },
        "guide": {},
    }


class FakeInvoker:
    def __init__(
        self,
        result,
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

class MCPRobinhoodEntryFundsReaderTests(
    unittest.TestCase
):
    def test_decodes_cash_and_unleveraged_buying_power(
        self,
    ) -> None:
        result = (
            decode_robinhood_entry_funds(
                portfolio_payload(
                    cash="90.75",
                    buying_power="999.00",
                    unleveraged_buying_power=(
                        "90.7500"
                    ),
                )
            )
        )

        self.assertEqual(
            result.cash,
            Decimal("90.75"),
        )

        self.assertEqual(
            result.buying_power,
            Decimal("90.7500"),
        )

    def test_reader_calls_get_portfolio_for_account(
        self,
    ) -> None:
        invoker = FakeInvoker(
            portfolio_payload()
        )

        reader = (
            MCPRobinhoodEntryFundsReader(
                invoker
            )
        )

        result = reader.read(
            account_number=(
                "account-0000"
            )
        )

        self.assertEqual(
            result.cash,
            Decimal("90.75"),
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_portfolio",
                    {
                        "account_number":
                            "account-0000",
                    },
                ),
            ],
        )

    def test_missing_cash_is_rejected(
        self,
    ) -> None:
        payload = (
            portfolio_payload()
        )

        del payload["data"]["cash"]

        with self.assertRaisesRegex(
            ValueError,
            "cash",
        ):
            decode_robinhood_entry_funds(
                payload
            )

    def test_missing_unleveraged_buying_power_is_rejected(
        self,
    ) -> None:
        payload = (
            portfolio_payload()
        )

        del (
            payload["data"]
            ["buying_power"]
            ["unleveraged_buying_power"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "unleveraged_buying_power",
        ):
            decode_robinhood_entry_funds(
                payload
            )

    def test_non_usd_portfolio_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "currency must be USD",
        ):
            decode_robinhood_entry_funds(
                portfolio_payload(
                    currency="EUR"
                )
            )

    def test_negative_cash_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cash",
        ):
            decode_robinhood_entry_funds(
                portfolio_payload(
                    cash="-1"
                )
            )

    def test_malformed_buying_power_is_rejected(
        self,
    ) -> None:
        payload = (
            portfolio_payload()
        )

        payload["data"][
            "buying_power"
        ] = "90.75"

        with self.assertRaisesRegex(
            ValueError,
            "buying_power must be "
            "a mapping",
        ):
            decode_robinhood_entry_funds(
                payload
            )

    def test_transport_error_propagates(
        self,
    ) -> None:
        class FailingInvoker:
            def call_tool(
                self,
                tool_name,
                arguments,
            ):
                raise RuntimeError(
                    "portfolio unavailable"
                )

        reader = (
            MCPRobinhoodEntryFundsReader(
                FailingInvoker()
            )
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "portfolio unavailable",
        ):
            reader.read(
                account_number=(
                    "account-0000"
                )
            )