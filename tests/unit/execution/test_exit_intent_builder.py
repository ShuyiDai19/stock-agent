import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.execution import (
    ExitReason,
    build_exit_intent,
)
from stock_agent.risk import (
    TrailingStopDecision,
    TrailingStopEvaluation,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)


class ExitIntentBuilderTests(unittest.TestCase):
    def make_state(self) -> PositionRuntimeState:
        opened_at = datetime(
            2026,
            8,
            17,
            14,
            0,
            tzinfo=timezone.utc,
        )

        last_quote_at = datetime(
            2026,
            8,
            17,
            14,
            30,
            tzinfo=timezone.utc,
        )

        return PositionRuntimeState(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            opening_order_id="order-123",
            entry_price=Decimal("100"),
            remaining_quantity=Decimal("0.031"),
            opened_at=opened_at,
            highest_executable_bid=Decimal("110"),
            trailing_armed=True,
            trailing_armed_at=datetime(
                2026,
                8,
                17,
                14,
                15,
                tzinfo=timezone.utc,
            ),
            activation_gain_ratio=Decimal("0.04"),
            drawdown_ratio=Decimal("0.02"),
            last_quote_at=last_quote_at,
            last_reconciled_at=opened_at,
            status=PositionStateStatus.ACTIVE,
            option_id=None,
            historical_high_unknown=False,
            version=3,
        )

    def test_returns_none_for_hold_decision(self) -> None:
        state = self.make_state()

        evaluation = TrailingStopEvaluation(
            state=state,
            decision=TrailingStopDecision.HOLD,
            reason="trailing stop conditions were not met",
        )

        intent = build_exit_intent(
            evaluation,
        )

        self.assertIsNone(intent)

    def test_builds_exit_intent_for_exit_decision(self) -> None:
        state = self.make_state()

        evaluation = TrailingStopEvaluation(
            state=state,
            decision=TrailingStopDecision.EXIT,
            reason="trailing stop triggered",
        )

        intent = build_exit_intent(
            evaluation,
        )

        self.assertIsNotNone(intent)

        self.assertEqual(
            intent.position_id,
            state.position_id,
        )

        self.assertEqual(
            intent.account_number,
            state.account_number,
        )

        self.assertEqual(
            intent.asset_type,
            AssetType.EQUITY,
        )

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

        self.assertEqual(
            intent.triggered_at,
            state.last_quote_at,
        )

        self.assertIsNone(
            intent.option_id,
        )

    def test_uses_remaining_position_quantity(self) -> None:
        state = self.make_state()

        evaluation = TrailingStopEvaluation(
            state=state,
            decision=TrailingStopDecision.EXIT,
            reason="trailing stop triggered",
        )

        intent = build_exit_intent(
            evaluation,
        )

        self.assertEqual(
            intent.quantity,
            state.remaining_quantity,
        )


if __name__ == "__main__":
    unittest.main()