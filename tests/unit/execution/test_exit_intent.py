import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExitIntent,
    ExitReason,
)


class ExitIntentTests(unittest.TestCase):
    def make_intent(self) -> ExitIntent:
        return ExitIntent(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            reason=ExitReason.TRAILING_STOP,
            triggered_at=datetime(
                2026,
                8,
                17,
                20,
                0,
                tzinfo=timezone.utc,
            ),
            option_id=None,
        )

    def test_creates_valid_exit_intent(self) -> None:
        intent = self.make_intent()

        self.assertEqual(
            intent.symbol,
            "AAPL",
        )

        self.assertEqual(
            intent.quantity,
            Decimal("0.031"),
        )

        self.assertEqual(
            intent.reason,
            ExitReason.TRAILING_STOP,
        )

    def test_rejects_empty_position_id(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "position_id cannot be empty",
        ):
            ExitIntent(
                position_id=" ",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("1"),
                reason=ExitReason.TRAILING_STOP,
                triggered_at=datetime.now(timezone.utc),
            )

    def test_rejects_empty_symbol(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "symbol cannot be empty",
        ):
            ExitIntent(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol=" ",
                quantity=Decimal("1"),
                reason=ExitReason.TRAILING_STOP,
                triggered_at=datetime.now(timezone.utc),
            )

    def test_rejects_non_positive_quantity(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "quantity must be greater than zero",
        ):
            ExitIntent(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("0"),
                reason=ExitReason.TRAILING_STOP,
                triggered_at=datetime.now(timezone.utc),
            )

    def test_rejects_non_finite_quantity(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "quantity must be finite",
        ):
            ExitIntent(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("NaN"),
                reason=ExitReason.TRAILING_STOP,
                triggered_at=datetime.now(timezone.utc),
            )

    def test_rejects_naive_triggered_at(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "triggered_at must be timezone-aware",
        ):
            ExitIntent(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("1"),
                reason=ExitReason.TRAILING_STOP,
                triggered_at=datetime(
                    2026,
                    8,
                    17,
                    20,
                    0,
                ),
            )


if __name__ == "__main__":
    unittest.main()