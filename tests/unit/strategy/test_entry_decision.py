import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.risk.entry_portfolio import (
    EntryRiskReason,
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
    EntryConfirmationReason,
)
from stock_agent.strategy.entry_decision import (
    evaluate_entry_decision,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def market(
    symbol: str = "AAPL",
    *,
    price: str = "102",
    session_open: str = "100",
    vwap: str = "101",
    closes: tuple[str, str, str] = (
        "100",
        "101",
        "102",
    ),
) -> BullishEntrySnapshot:
    return BullishEntrySnapshot(
        symbol=symbol,
        price=Decimal(price),
        session_open=Decimal(
            session_open
        ),
        vwap=Decimal(vwap),
        recent_5m_closes=tuple(
            Decimal(value)
            for value in closes
        ),
        observed_at=_NOW,
    )


def request(
    symbol: str = "AAPL",
    *,
    opening_cost: str = "8",
) -> EntryRiskRequest:
    return EntryRiskRequest(
        symbol=symbol,
        asset_type=AssetType.EQUITY,
        opening_cost=Decimal(
            opening_cost
        ),
    )


def position(
    symbol: str,
    *,
    opening_cost: str = "8",
) -> OpenPositionRiskSnapshot:
    return OpenPositionRiskSnapshot(
        symbol=symbol,
        asset_type=AssetType.EQUITY,
        opening_cost=Decimal(
            opening_cost
        ),
    )


class EntryDecisionTests(
    unittest.TestCase
):
    def test_approves_when_signal_and_risk_pass(
        self,
    ) -> None:
        decision = evaluate_entry_decision(
            market=market(),
            request=request(),
            open_positions=(),
        )

        self.assertTrue(
            decision.approved
        )

        self.assertTrue(
            decision.confirmation.approved
        )

        self.assertTrue(
            decision.risk.approved
        )

    def test_rejects_when_confirmation_fails(
        self,
    ) -> None:
        decision = evaluate_entry_decision(
            market=market(
                price="100",
                session_open="100",
                vwap="99",
            ),
            request=request(),
            open_positions=(),
        )

        self.assertFalse(
            decision.approved
        )

        self.assertIn(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_OPEN,
            decision.confirmation.reasons,
        )

        self.assertTrue(
            decision.risk.approved
        )

    def test_rejects_when_portfolio_risk_fails(
        self,
    ) -> None:
        decision = evaluate_entry_decision(
            market=market(),
            request=request(),
            open_positions=(
                position("AAPL"),
            ),
        )

        self.assertFalse(
            decision.approved
        )

        self.assertTrue(
            decision.confirmation.approved
        )

        self.assertIn(
            EntryRiskReason
            .DUPLICATE_UNDERLYING,
            decision.risk.reasons,
        )

    def test_reports_signal_and_risk_failures_together(
        self,
    ) -> None:
        decision = evaluate_entry_decision(
            market=market(
                price="99",
                session_open="100",
                vwap="101",
                closes=(
                    "103",
                    "102",
                    "101",
                ),
            ),
            request=request(),
            open_positions=(
                position("AAPL"),
            ),
        )

        self.assertFalse(
            decision.approved
        )

        self.assertIn(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_OPEN,
            decision.confirmation.reasons,
        )

        self.assertIn(
            EntryConfirmationReason
            .PRICE_NOT_ABOVE_VWAP,
            decision.confirmation.reasons,
        )

        self.assertIn(
            EntryConfirmationReason
            .TWO_CONSECUTIVE_LOWER_CLOSES,
            decision.confirmation.reasons,
        )

        self.assertIn(
            EntryRiskReason
            .DUPLICATE_UNDERLYING,
            decision.risk.reasons,
        )

    def test_rejects_mismatched_symbol_inputs(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "symbol must match",
        ):
            evaluate_entry_decision(
                market=market(
                    symbol="AAPL"
                ),
                request=request(
                    symbol="MSFT"
                ),
                open_positions=(),
            )


if __name__ == "__main__":
    unittest.main()