import unittest
from datetime import UTC, datetime
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


class PositionRuntimeStateTests(unittest.TestCase):
    def make_state(
        self,
        **overrides,
    ) -> PositionRuntimeState:
        now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)

        values = {
            "position_id": "account:equity:AAPL:order-123",
            "account_number": "946000000",
            "asset_type": AssetType.EQUITY,
            "symbol": "AAPL",
            "opening_order_id": "order-123",
            "entry_price": Decimal("321.66"),
            "remaining_quantity": Decimal("0.031089"),
            "opened_at": now,
            "highest_executable_bid": Decimal("337.68"),
            "trailing_armed": True,
            "trailing_armed_at": now,
            "activation_gain_ratio": Decimal("0.04"),
            "drawdown_ratio": Decimal("0.02"),
            "last_quote_at": now,
            "last_reconciled_at": now,
        }
        values.update(overrides)

        return PositionRuntimeState(**values)

    def test_normalizes_symbol(self) -> None:
        state = self.make_state(symbol=" aapl ")

        self.assertEqual(state.symbol, "AAPL")

    def test_requires_armed_timestamp_when_trailing_is_armed(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "trailing_armed_at is required",
        ):
            self.make_state(
                trailing_armed=True,
                trailing_armed_at=None,
            )

    def test_rejects_armed_timestamp_when_trailing_is_not_armed(self) -> None:
        now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)

        with self.assertRaisesRegex(
            ValueError,
            "trailing_armed_at must be empty",
        ):
            self.make_state(
                trailing_armed=False,
                trailing_armed_at=now,
            )

    def test_option_state_requires_option_id(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "option_id is required",
        ):
            self.make_state(
                asset_type=AssetType.OPTION,
                option_id=None,
            )

    def test_closed_state_requires_zero_remaining_quantity(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "closed position state must have zero",
        ):
            self.make_state(
                status=PositionStateStatus.CLOSED,
                remaining_quantity=Decimal("0.01"),
            )

    def test_allows_closed_state_with_zero_quantity(self) -> None:
        state = self.make_state(
            status=PositionStateStatus.CLOSED,
            remaining_quantity=Decimal("0"),
        )

        self.assertEqual(state.status, PositionStateStatus.CLOSED)
        self.assertEqual(state.remaining_quantity, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
