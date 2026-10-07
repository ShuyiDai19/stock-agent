import unittest

from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.entry_execution_limits import (
    EquityEntryOrderLimitExceededError,
    equity_entry_order_notional,
    require_live_equity_entry_order_limit,
)
from stock_agent.strategy.entry_execution import (
    EquityEntryExecutionMode,
    EquityEntryExecutionPlan,
)


_OBSERVED_AT = datetime(
    2026,
    10,
    5,
    18,
    0,
    tzinfo=timezone.utc,
)


class EquityEntryExecutionLimitsTests(
    unittest.TestCase
):
    def test_fractional_five_dollars_is_allowed(
        self,
    ) -> None:
        plan = EquityEntryExecutionPlan(
            symbol="AAPL",
            mode=(
                EquityEntryExecutionMode
                .FRACTIONAL_MARKET
            ),
            budget=Decimal("5"),
            dollar_amount=Decimal("5"),
            quote_observed_at=(
                _OBSERVED_AT
            ),
        )

        notional = (
            require_live_equity_entry_order_limit(
                plan
            )
        )

        self.assertEqual(
            notional,
            Decimal("5"),
        )

    def test_fractional_above_five_dollars_is_blocked(
        self,
    ) -> None:
        plan = EquityEntryExecutionPlan(
            symbol="AAPL",
            mode=(
                EquityEntryExecutionMode
                .FRACTIONAL_MARKET
            ),
            budget=Decimal("5.01"),
            dollar_amount=Decimal("5.01"),
            quote_observed_at=(
                _OBSERVED_AT
            ),
        )

        with self.assertRaises(
            EquityEntryOrderLimitExceededError
        ):
            require_live_equity_entry_order_limit(
                plan
            )

    def test_whole_share_notional_is_quantity_times_limit_price(
        self,
    ) -> None:
        plan = EquityEntryExecutionPlan(
            symbol="TEST",
            mode=(
                EquityEntryExecutionMode
                .WHOLE_SHARE_LIMIT
            ),
            budget=Decimal("5"),
            quantity=Decimal("2"),
            limit_price=Decimal("2.50"),
            quote_observed_at=(
                _OBSERVED_AT
            ),
        )

        self.assertEqual(
            equity_entry_order_notional(
                plan
            ),
            Decimal("5.00"),
        )

    def test_whole_share_above_five_dollars_is_blocked(
        self,
    ) -> None:
        plan = EquityEntryExecutionPlan(
            symbol="TEST",
            mode=(
                EquityEntryExecutionMode
                .WHOLE_SHARE_LIMIT
            ),
            budget=Decimal("6"),
            quantity=Decimal("2"),
            limit_price=Decimal("3"),
            quote_observed_at=(
                _OBSERVED_AT
            ),
        )

        with self.assertRaises(
            EquityEntryOrderLimitExceededError
        ):
            require_live_equity_entry_order_limit(
                plan
            )


if __name__ == "__main__":
    unittest.main()