import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from stock_agent.brokers.robinhood.entry_review import (
    RobinhoodEntryReviewMismatchError,
    review_robinhood_equity_entry,
)
from stock_agent.strategy.entry_execution import (
    EquityEntryExecutionMode,
    EquityEntryExecutionPlan,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


class FakeMCPInvoker:
    def __init__(
        self,
        result: Any,
    ) -> None:
        self.result = result
        self.calls = []

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


def limit_plan(
) -> EquityEntryExecutionPlan:
    return EquityEntryExecutionPlan(
        symbol="SOFI",
        mode=(
            EquityEntryExecutionMode
            .WHOLE_SHARE_LIMIT
        ),
        budget=Decimal("8"),
        quantity=Decimal("1"),
        limit_price=Decimal("7.50"),
        quote_observed_at=_NOW,
    )


def fractional_plan(
) -> EquityEntryExecutionPlan:
    return EquityEntryExecutionPlan(
        symbol="AAPL",
        mode=(
            EquityEntryExecutionMode
            .FRACTIONAL_MARKET
        ),
        budget=Decimal("8"),
        dollar_amount=Decimal("8"),
        quote_observed_at=_NOW,
    )


class RobinhoodEquityEntryReviewTests(
    unittest.TestCase
):
    def test_reviews_whole_share_limit_entry(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "data": {
                    "symbol": "SOFI",
                    "side": "buy",
                    "type": "limit",
                    "quantity": "1",
                    "limit_price": "7.5",
                    "order_checks": {},
                    "market_data_disclosure": (
                        "fake market disclosure"
                    ),
                }
            }
        )

        review = review_robinhood_equity_entry(
            invoker,
            account_number="agentic-account",
            plan=limit_plan(),
        )

        self.assertTrue(
            review.approved
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "review_equity_order",
                    {
                        "account_number": (
                            "agentic-account"
                        ),
                        "symbol": "SOFI",
                        "side": "buy",
                        "time_in_force": "gfd",
                        "market_hours": (
                            "regular_hours"
                        ),
                        "type": "limit",
                        "quantity": "1",
                        "limit_price": "7.50",
                    },
                )
            ],
        )

        self.assertEqual(
            review.market_data_disclosure,
            "fake market disclosure",
        )

    def test_reviews_fractional_market_entry(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "data": {
                    "symbol": "AAPL",
                    "side": "buy",
                    "type": "market",
                    "dollar_amount": "8.00",
                    "order_checks": {},
                }
            }
        )

        review = review_robinhood_equity_entry(
            invoker,
            account_number="agentic-account",
            plan=fractional_plan(),
        )

        self.assertTrue(
            review.approved
        )

        self.assertEqual(
            invoker.calls[0][1],
            {
                "account_number": (
                    "agentic-account"
                ),
                "symbol": "AAPL",
                "side": "buy",
                "time_in_force": "gfd",
                "market_hours": (
                    "regular_hours"
                ),
                "type": "market",
                "dollar_amount": "8",
            },
        )

    def test_broker_order_check_rejects_entry(
        self,
    ) -> None:
        checks = {
            "example_alert": {
                "detail": (
                    "insufficient buying power"
                )
            }
        }

        invoker = FakeMCPInvoker(
            {
                "data": {
                    "symbol": "AAPL",
                    "side": "buy",
                    "type": "market",
                    "dollar_amount": "8",
                    "order_checks": checks,
                }
            }
        )

        review = review_robinhood_equity_entry(
            invoker,
            account_number="agentic-account",
            plan=fractional_plan(),
        )

        self.assertFalse(
            review.approved
        )

        self.assertEqual(
            review.order_checks,
            checks,
        )

    def test_rejects_mismatched_review(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "data": {
                    "symbol": "MSFT",
                    "side": "buy",
                    "type": "market",
                    "dollar_amount": "8",
                    "order_checks": {},
                }
            }
        )

        with self.assertRaisesRegex(
            RobinhoodEntryReviewMismatchError,
            "symbol does not match",
        ):
            review_robinhood_equity_entry(
                invoker,
                account_number="agentic-account",
                plan=fractional_plan(),
            )

    def test_rejects_invalid_review_shape(
        self,
    ) -> None:
        invoker = FakeMCPInvoker(
            {
                "unexpected": {}
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "must contain data",
        ):
            review_robinhood_equity_entry(
                invoker,
                account_number="agentic-account",
                plan=fractional_plan(),
            )


if __name__ == "__main__":
    unittest.main()