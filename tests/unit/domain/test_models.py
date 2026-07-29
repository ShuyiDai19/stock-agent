import unittest
from datetime import UTC, datetime
from decimal import Decimal

from stock_agent.domain import (
    AccountSnapshot,
    AccountType,
    AssetType,
    MarketSnapshot,
    OrderSide,
    PositionEffect,
    TradeIntent,
)


class TradeIntentTests(unittest.TestCase):
    def test_normalizes_symbol(self) -> None:
        intent = TradeIntent(
            symbol=" aapl ",
            asset_type=AssetType.EQUITY,
            side=OrderSide.BUY,
            position_effect=PositionEffect.OPEN,
            notional=Decimal("10"),
        )

        self.assertEqual(intent.symbol, "AAPL")

    def test_requires_exactly_one_sizing_method(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            TradeIntent(
                symbol="AAPL",
                asset_type=AssetType.EQUITY,
                side=OrderSide.BUY,
                position_effect=PositionEffect.OPEN,
            )

    def test_option_requires_option_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "option_id is required"):
            TradeIntent(
                symbol="AAPL",
                asset_type=AssetType.OPTION,
                side=OrderSide.BUY,
                position_effect=PositionEffect.OPEN,
                quantity=Decimal("1"),
            )


class AccountSnapshotTests(unittest.TestCase):
    def test_masks_account_number(self) -> None:
        snapshot = AccountSnapshot(
            account_number="946000000",
            account_type=AccountType.CASH,
            agentic_allowed=True,
            portfolio_value=Decimal("100.74"),
            cash=Decimal("90.74"),
            buying_power=Decimal("90.74"),
            captured_at=datetime.now(UTC),
        )

        self.assertEqual(snapshot.masked_account_number, "••••0000")

    def test_rejects_negative_cash(self) -> None:
        with self.assertRaisesRegex(ValueError, "cash cannot be negative"):
            AccountSnapshot(
                account_number="946000000",
                account_type=AccountType.CASH,
                agentic_allowed=True,
                portfolio_value=Decimal("100"),
                cash=Decimal("-1"),
                buying_power=Decimal("90"),
                captured_at=datetime.now(UTC),
            )


class MarketSnapshotTests(unittest.TestCase):
    def test_calculates_spread_ratio(self) -> None:
        snapshot = MarketSnapshot(
            symbol="AAPL",
            current_price=Decimal("100"),
            bid=Decimal("99"),
            ask=Decimal("101"),
            session_open=Decimal("98"),
            captured_at=datetime.now(UTC),
        )

        self.assertEqual(snapshot.midpoint, Decimal("100"))
        self.assertEqual(snapshot.spread_ratio, Decimal("0.02"))


if __name__ == "__main__":
    unittest.main()
