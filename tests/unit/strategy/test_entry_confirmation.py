import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
    EntryConfirmationReason,
    evaluate_bullish_entry_confirmation,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def make_snapshot(
    *,
    price: Decimal = Decimal("102"),
    session_open: Decimal = Decimal("100"),
    vwap: Decimal = Decimal("101"),
    closes: tuple[
        Decimal,
        Decimal,
        Decimal,
    ] = (
        Decimal("100"),
        Decimal("101"),
        Decimal("102"),
    ),
) -> BullishEntrySnapshot:
    return BullishEntrySnapshot(
        symbol="AAPL",
        price=price,
        session_open=session_open,
        vwap=vwap,
        recent_5m_closes=closes,
        observed_at=_NOW,
    )


class BullishEntryConfirmationTests(
    unittest.TestCase
):
    def test_approves_when_all_confirmation_rules_pass(
        self,
    ) -> None:
        decision = (
            evaluate_bullish_entry_confirmation(
                make_snapshot()
            )
        )

        self.assertTrue(
            decision.approved
        )

        self.assertEqual(
            decision.reasons,
            frozenset(),
        )

    def test_requires_price_strictly_above_open(
        self,
    ) -> None:
        decision = (
            evaluate_bullish_entry_confirmation(
                make_snapshot(
                    price=Decimal("100"),
                    session_open=Decimal("100"),
                    vwap=Decimal("99"),
                )
            )
        )

        self.assertFalse(
            decision.approved
        )

        self.assertIn(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_OPEN,
            decision.reasons,
        )

    def test_requires_price_strictly_above_vwap(
        self,
    ) -> None:
        decision = (
            evaluate_bullish_entry_confirmation(
                make_snapshot(
                    price=Decimal("101"),
                    session_open=Decimal("100"),
                    vwap=Decimal("101"),
                )
            )
        )

        self.assertFalse(
            decision.approved
        )

        self.assertIn(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_VWAP,
            decision.reasons,
        )

    def test_rejects_two_consecutive_lower_closes(
        self,
    ) -> None:
        decision = (
            evaluate_bullish_entry_confirmation(
                make_snapshot(
                    closes=(
                        Decimal("103"),
                        Decimal("102"),
                        Decimal("101"),
                    )
                )
            )
        )

        self.assertFalse(
            decision.approved
        )

        self.assertIn(
            EntryConfirmationReason
            .TWO_CONSECUTIVE_LOWER_CLOSES,
            decision.reasons,
        )

    def test_single_lower_close_does_not_reject_entry(
        self,
    ) -> None:
        decision = (
            evaluate_bullish_entry_confirmation(
                make_snapshot(
                    closes=(
                        Decimal("103"),
                        Decimal("102"),
                        Decimal("102.5"),
                    )
                )
            )
        )

        self.assertTrue(
            decision.approved
        )

    def test_collects_multiple_failed_rules(
        self,
    ) -> None:
        decision = (
            evaluate_bullish_entry_confirmation(
                make_snapshot(
                    price=Decimal("99"),
                    session_open=Decimal("100"),
                    vwap=Decimal("101"),
                    closes=(
                        Decimal("103"),
                        Decimal("102"),
                        Decimal("101"),
                    ),
                )
            )
        )

        self.assertEqual(
            decision.reasons,
            frozenset(
                {
                    EntryConfirmationReason
                    .PRICE_NOT_ABOVE_OPEN,
                    EntryConfirmationReason
                    .PRICE_NOT_ABOVE_VWAP,
                    EntryConfirmationReason
                    .TWO_CONSECUTIVE_LOWER_CLOSES,
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()