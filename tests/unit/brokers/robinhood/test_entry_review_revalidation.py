import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.entry_review import (
    RobinhoodEquityEntryReview,
    revalidate_robinhood_equity_entry_review,
)
from stock_agent.strategy.entry_execution import (
    EntryExecutionNotAllowedError,
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


def review(
    plan,
    *,
    bid: str,
    ask: str,
    observed_at: datetime = _NOW,
    approved: bool = True,
) -> RobinhoodEquityEntryReview:
    timestamp = (
        observed_at
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )

    return RobinhoodEquityEntryReview(
        plan=plan,
        approved=approved,
        order_checks=(
            {}
            if approved
            else {
                "test_alert": {
                    "detail": "not allowed"
                }
            }
        ),
        quote_data={
            "bid_price": bid,
            "ask_price": ask,
            "venue_bid_time": timestamp,
            "venue_ask_time": timestamp,
        },
        market_data_disclosure=None,
    )


class EntryReviewRevalidationTests(
    unittest.TestCase
):
    def test_accepts_fresh_tight_fractional_market_quote(
        self,
    ) -> None:
        validated_quote = (
            revalidate_robinhood_equity_entry_review(
                review(
                    fractional_plan(),
                    bid="199.90",
                    ask="200.10",
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            validated_quote.bid,
            Decimal("199.90"),
        )

        self.assertEqual(
            validated_quote.ask,
            Decimal("200.10"),
        )

    def test_rejects_wide_review_spread(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "spread exceeds",
        ):
            revalidate_robinhood_equity_entry_review(
                review(
                    fractional_plan(),
                    bid="199",
                    ask="200",
                ),
                evaluated_at=_NOW,
            )

    def test_rejects_stale_review_quote(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "review quote is stale",
        ):
            revalidate_robinhood_equity_entry_review(
                review(
                    fractional_plan(),
                    bid="199.90",
                    ask="200.10",
                    observed_at=(
                        _NOW
                        - timedelta(
                            seconds=31
                        )
                    ),
                ),
                evaluated_at=_NOW,
            )

    def test_rejects_limit_when_ask_moves_above_limit(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "ask moved above",
        ):
            revalidate_robinhood_equity_entry_review(
                review(
                    limit_plan(),
                    bid="7.50",
                    ask="7.51",
                ),
                evaluated_at=_NOW,
            )

    def test_accepts_limit_when_ask_remains_at_limit(
        self,
    ) -> None:
        validated_quote = (
            revalidate_robinhood_equity_entry_review(
                review(
                    limit_plan(),
                    bid="7.49",
                    ask="7.50",
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            validated_quote.ask,
            Decimal("7.50"),
        )

    def test_rejects_missing_review_quote(
        self,
    ) -> None:
        broker_review = (
            RobinhoodEquityEntryReview(
                plan=fractional_plan(),
                approved=True,
                order_checks={},
                quote_data=None,
                market_data_disclosure=None,
            )
        )

        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "did not contain live quote",
        ):
            revalidate_robinhood_equity_entry_review(
                broker_review,
                evaluated_at=_NOW,
            )


if __name__ == "__main__":
    unittest.main()