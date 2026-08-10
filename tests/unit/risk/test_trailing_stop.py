import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.risk import (
    TrailingStopDecision,
    evaluate_trailing_stop,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)


class TrailingStopEvaluatorTests(unittest.TestCase):
    def make_state(self) -> PositionRuntimeState:
        opened_at = datetime(
            2026,
            8,
            1,
            14,
            0,
            tzinfo=timezone.utc,
        )

        return PositionRuntimeState(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            opening_order_id="order-123",
            entry_price=Decimal("100"),
            remaining_quantity=Decimal("1"),
            opened_at=opened_at,
            highest_executable_bid=Decimal("100"),
            trailing_armed=False,
            trailing_armed_at=None,
            activation_gain_ratio=Decimal("0.04"),
            drawdown_ratio=Decimal("0.02"),
            last_quote_at=opened_at,
            last_reconciled_at=opened_at,
            status=PositionStateStatus.ACTIVE,
            option_id=None,
            historical_high_unknown=False,
            version=1,
        )

    def test_updates_highest_executable_bid(self) -> None:
        original = self.make_state()
        observed_at = original.last_quote_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("103"),
            observed_at=observed_at,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("103"),
        )
        self.assertEqual(
            result.state.last_quote_at,
            observed_at,
        )
        self.assertEqual(
            result.state.version,
            2,
        )
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        # Pure function:
        # the original state must remain unchanged.
        self.assertEqual(
            original.highest_executable_bid,
            Decimal("100"),
        )
        self.assertEqual(
            original.version,
            1,
        )

    def test_does_not_lower_highest_executable_bid(self) -> None:
        original = self.make_state()
        observed_at = original.last_quote_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("99"),
            observed_at=observed_at,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("100"),
        )
        self.assertEqual(
            result.state.version,
            2,
        )
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

    def test_rejects_non_positive_bid(self) -> None:
        state = self.make_state()

        with self.assertRaisesRegex(
            ValueError,
            "latest_bid must be greater than zero",
        ):
            evaluate_trailing_stop(
                state,
                latest_bid=Decimal("0"),
                observed_at=(
                    state.last_quote_at
                    + timedelta(minutes=5)
                ),
            )

    def test_rejects_inactive_position(self) -> None:
        state = replace(
            self.make_state(),
            status=PositionStateStatus.CLOSED,
            remaining_quantity=Decimal("0"),
        )

        with self.assertRaisesRegex(
            ValueError,
            "active position",
        ):
            evaluate_trailing_stop(
                state,
                latest_bid=Decimal("101"),
                observed_at=(
                    state.last_quote_at
                    + timedelta(minutes=5)
                ),
            )

    def test_arms_trailing_at_activation_threshold(self) -> None:
        original = self.make_state()
        observed_at = original.last_quote_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("104"),
            observed_at=observed_at,
        )

        self.assertTrue(result.state.trailing_armed)
        self.assertEqual(
            result.state.trailing_armed_at,
            observed_at,
        )
        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("104"),
        )
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )
        self.assertEqual(
            result.reason,
            "trailing stop armed",
        )

        # Original state remains unchanged.
        self.assertFalse(original.trailing_armed)
        self.assertIsNone(original.trailing_armed_at)

    def test_newly_armed_trailing_does_not_exit_on_same_quote(
        self,
    ) -> None:
        original = self.make_state()
        observed_at = original.last_quote_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("104"),
            observed_at=observed_at,
        )

        # This quote reaches the +4% activation threshold.
        self.assertTrue(result.state.trailing_armed)
        self.assertEqual(
            result.state.trailing_armed_at,
            observed_at,
        )

        # Arming trailing must not trigger an exit
        # during the same evaluation.
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("104"),
        )

    def test_does_not_arm_below_activation_threshold(self) -> None:
        original = self.make_state()
        observed_at = original.last_quote_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("103.99"),
            observed_at=observed_at,
        )

        self.assertFalse(result.state.trailing_armed)
        self.assertIsNone(result.state.trailing_armed_at)
        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("103.99"),
        )
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

    def test_armed_trailing_does_not_disarm_below_threshold(self) -> None:
        original = self.make_state()

        armed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        armed_state = replace(
            original,
            highest_executable_bid=Decimal("104"),
            trailing_armed=True,
            trailing_armed_at=armed_at,
            last_quote_at=armed_at,
            version=2,
        )

        observed_at = armed_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            armed_state,
            latest_bid=Decimal("103"),
            observed_at=observed_at,
        )

        self.assertTrue(result.state.trailing_armed)
        self.assertEqual(
            result.state.trailing_armed_at,
            armed_at,
        )
        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("104"),
        )
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )


    def test_armed_trailing_does_not_overwrite_armed_at(
        self,
    ) -> None:
        original = self.make_state()

        armed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        armed_state = replace(
            original,
            highest_executable_bid=Decimal("104"),
            trailing_armed=True,
            trailing_armed_at=armed_at,
            last_quote_at=armed_at,
            version=2,
        )

        observed_at = armed_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            armed_state,
            latest_bid=Decimal("106"),
            observed_at=observed_at,
        )

        self.assertTrue(result.state.trailing_armed)

        # The timestamp records when trailing was first armed.
        self.assertEqual(
            result.state.trailing_armed_at,
            armed_at,
        )

        # A new high should still be recorded normally.
        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("106"),
        )

        self.assertEqual(
            result.state.last_quote_at,
            observed_at,
        )
        self.assertEqual(
            result.state.version,
            3,
        )

    def test_holds_just_below_drawdown_threshold(self) -> None:
        original = self.make_state()

        armed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        armed_state = replace(
            original,
            highest_executable_bid=Decimal("110"),
            trailing_armed=True,
            trailing_armed_at=armed_at,
            last_quote_at=armed_at,
            version=2,
        )

        observed_at = armed_at + timedelta(minutes=5)

        # 1.99% drawdown from 110:
        # 110 * (1 - 0.0199) = 107.811
        result = evaluate_trailing_stop(
            armed_state,
            latest_bid=Decimal("107.811"),
            observed_at=observed_at,
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )
        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("110"),
        )
        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

    def test_exits_at_exact_drawdown_threshold(self) -> None:
        original = self.make_state()

        armed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        armed_state = replace(
            original,
            highest_executable_bid=Decimal("110"),
            trailing_armed=True,
            trailing_armed_at=armed_at,
            last_quote_at=armed_at,
            version=2,
        )

        observed_at = armed_at + timedelta(minutes=5)

        # Exactly 2% drawdown from 110:
        # 110 * (1 - 0.02) = 107.80
        result = evaluate_trailing_stop(
            armed_state,
            latest_bid=Decimal("107.80"),
            observed_at=observed_at,
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.EXIT,
        )
        self.assertEqual(
            result.reason,
            "trailing stop triggered",
        )

        # EXIT is only a decision.
        # The position is not closed until execution succeeds.
        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("110"),
        )

    def test_unarmed_position_does_not_exit_on_large_drawdown(self) -> None:
        original = self.make_state()
        observed_at = original.last_quote_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("90"),
            observed_at=observed_at,
        )

        self.assertFalse(result.state.trailing_armed)
        self.assertIsNone(result.state.trailing_armed_at)

        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

    def test_unknown_historical_high_suppresses_trailing_exit(
        self,
    ) -> None:
        original = self.make_state()

        armed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        uncertain_state = replace(
            original,
            highest_executable_bid=Decimal("110"),
            trailing_armed=True,
            trailing_armed_at=armed_at,
            historical_high_unknown=True,
            last_quote_at=armed_at,
            version=2,
        )

        observed_at = armed_at + timedelta(minutes=5)

        result = evaluate_trailing_stop(
            uncertain_state,
            latest_bid=Decimal("107"),
            observed_at=observed_at,
        )

        # This would normally exceed the 2% drawdown threshold,
        # but the historical high is not authoritative.
        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            result.state.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertTrue(
            result.state.historical_high_unknown,
        )

    def test_unknown_historical_high_remains_unknown_after_new_quote(
        self,
    ) -> None:
        original = replace(
            self.make_state(),
            historical_high_unknown=True,
        )

        observed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("103"),
            observed_at=observed_at,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("103"),
        )

        self.assertTrue(
            result.state.historical_high_unknown,
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

    def test_unknown_historical_high_can_still_arm_trailing(
        self,
    ) -> None:
        original = replace(
            self.make_state(),
            historical_high_unknown=True,
        )

        observed_at = (
            original.last_quote_at
            + timedelta(minutes=5)
        )

        result = evaluate_trailing_stop(
            original,
            latest_bid=Decimal("104"),
            observed_at=observed_at,
        )

        self.assertTrue(
            result.state.trailing_armed,
        )

        self.assertEqual(
            result.state.trailing_armed_at,
            observed_at,
        )

        self.assertTrue(
            result.state.historical_high_unknown,
        )

        self.assertEqual(
            result.state.highest_executable_bid,
            Decimal("104"),
        )

        self.assertEqual(
            result.decision,
            TrailingStopDecision.HOLD,
        )

        self.assertEqual(
            result.reason,
            "trailing stop armed",
        )

if __name__ == "__main__":
    unittest.main()