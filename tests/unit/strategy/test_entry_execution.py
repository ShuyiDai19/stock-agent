import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal

from stock_agent.strategy.entry_execution import (
    EntryExecutionNotAllowedError,
    EquityEntryExecutionMode,
    EquityExecutionQuote,
    build_equity_entry_execution_plan,
)
from stock_agent.strategy.entry_proposal import (
    EquityEntryProposal,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def proposal(
    *,
    symbol: str = "AAPL",
    budget: str = "8",
    reference_price: str = "100",
) -> EquityEntryProposal:
    budget_value = Decimal(
        budget
    )

    price_value = Decimal(
        reference_price
    )

    return EquityEntryProposal(
        symbol=symbol,
        budget=budget_value,
        reference_price=price_value,
        estimated_quantity=(
            budget_value / price_value
        ),
        proposed_at=_NOW,
    )


def quote(
    *,
    symbol: str = "AAPL",
    bid: str = "7.49",
    ask: str = "7.50",
    observed_at: datetime = _NOW,
) -> EquityExecutionQuote:
    return EquityExecutionQuote(
        symbol=symbol,
        bid=Decimal(bid),
        ask=Decimal(ask),
        observed_at=observed_at,
    )


class EquityEntryExecutionTests(
    unittest.TestCase
):
    def test_uses_limit_when_whole_share_fits_budget(
        self,
    ) -> None:
        plan = (
            build_equity_entry_execution_plan(
                proposal(
                    budget="8",
                    reference_price="7.50",
                ),
                quote(),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            plan.mode,
            EquityEntryExecutionMode
            .WHOLE_SHARE_LIMIT,
        )

        self.assertEqual(
            plan.quantity,
            Decimal("1"),
        )

        self.assertEqual(
            plan.limit_price,
            Decimal("7.50"),
        )

        self.assertIsNone(
            plan.dollar_amount
        )

    def test_uses_maximum_whole_shares_within_budget(
        self,
    ) -> None:
        plan = (
            build_equity_entry_execution_plan(
                proposal(
                    budget="10",
                    reference_price="4",
                ),
                quote(
                    bid="4",
                    ask="4",
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            plan.quantity,
            Decimal("2"),
        )

        self.assertEqual(
            plan.quantity
            * plan.limit_price,
            Decimal("8"),
        )

    def test_uses_fractional_market_for_expensive_stock(
        self,
    ) -> None:
        plan = (
            build_equity_entry_execution_plan(
                proposal(
                    budget="8",
                    reference_price="200",
                ),
                quote(
                    bid="199.90",
                    ask="200.10",
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            plan.mode,
            EquityEntryExecutionMode
            .FRACTIONAL_MARKET,
        )

        self.assertEqual(
            plan.dollar_amount,
            Decimal("8"),
        )

        self.assertIsNone(
            plan.quantity
        )

        self.assertIsNone(
            plan.limit_price
        )

    def test_rejects_wide_spread(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "spread exceeds",
        ):
            build_equity_entry_execution_plan(
                proposal(
                    budget="8",
                    reference_price="100",
                ),
                quote(
                    bid="99",
                    ask="100",
                ),
                evaluated_at=_NOW,
            )

    def test_rejects_stale_quote(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "quote is stale",
        ):
            build_equity_entry_execution_plan(
                proposal(),
                quote(
                    observed_at=(
                        _NOW
                        - timedelta(
                            seconds=31
                        )
                    )
                ),
                evaluated_at=_NOW,
            )

    def test_rejects_symbol_mismatch(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryExecutionNotAllowedError,
            "symbol must match",
        ):
            build_equity_entry_execution_plan(
                proposal(
                    symbol="AAPL"
                ),
                quote(
                    symbol="MSFT"
                ),
                evaluated_at=_NOW,
            )


if __name__ == "__main__":
    unittest.main()