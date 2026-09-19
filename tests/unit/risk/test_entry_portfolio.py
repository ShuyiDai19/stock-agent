import unittest
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.risk.entry_portfolio import (
    EntryRiskReason,
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
    evaluate_entry_portfolio_risk,
)


def position(
    symbol: str,
    *,
    asset_type: AssetType = AssetType.EQUITY,
    opening_cost: str = "8",
) -> OpenPositionRiskSnapshot:
    return OpenPositionRiskSnapshot(
        symbol=symbol,
        asset_type=asset_type,
        opening_cost=Decimal(
            opening_cost
        ),
    )


def request(
    symbol: str = "AAPL",
    *,
    asset_type: AssetType = AssetType.EQUITY,
    opening_cost: str = "8",
) -> EntryRiskRequest:
    return EntryRiskRequest(
        symbol=symbol,
        asset_type=asset_type,
        opening_cost=Decimal(
            opening_cost
        ),
    )


class EntryPortfolioRiskTests(
    unittest.TestCase
):
    def test_approves_valid_entry(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(),
            (
                position(
                    "MSFT",
                    opening_cost="8",
                ),
            ),
        )

        self.assertTrue(
            decision.approved
        )

    def test_rejects_opening_cost_below_minimum(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(
                opening_cost="4.99"
            ),
            (),
        )

        self.assertIn(
            EntryRiskReason
            .OPENING_COST_TOO_SMALL,
            decision.reasons,
        )

    def test_rejects_opening_cost_above_maximum(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(
                opening_cost="10.01"
            ),
            (),
        )

        self.assertIn(
            EntryRiskReason
            .OPENING_COST_TOO_LARGE,
            decision.reasons,
        )

    def test_rejects_third_open_position(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request("NVDA"),
            (
                position("AAPL"),
                position("MSFT"),
            ),
        )

        self.assertIn(
            EntryRiskReason
            .MAX_OPEN_POSITIONS_REACHED,
            decision.reasons,
        )

    def test_rejects_duplicate_underlying(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request("AAPL"),
            (
                position("AAPL"),
            ),
        )

        self.assertIn(
            EntryRiskReason
            .DUPLICATE_UNDERLYING,
            decision.reasons,
        )

    def test_rejects_second_option_position(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(
                "NVDA",
                asset_type=AssetType.OPTION,
            ),
            (
                position(
                    "AAPL",
                    asset_type=AssetType.OPTION,
                ),
            ),
        )

        self.assertIn(
            EntryRiskReason
            .MAX_OPTION_POSITIONS_REACHED,
            decision.reasons,
        )

    def test_rejects_total_cost_above_limit(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(
                "NVDA",
                opening_cost="6",
            ),
            (
                position(
                    "AAPL",
                    opening_cost="8",
                ),
                position(
                    "MSFT",
                    opening_cost="7",
                ),
            ),
        )

        self.assertIn(
            EntryRiskReason
            .TOTAL_OPENING_COST_EXCEEDED,
            decision.reasons,
        )

    def test_allows_exact_boundaries(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(
                "MSFT",
                opening_cost="10",
            ),
            (
                position(
                    "AAPL",
                    opening_cost="10",
                ),
            ),
        )

        self.assertTrue(
            decision.approved
        )

    def test_collects_multiple_failures(
        self,
    ) -> None:
        decision = evaluate_entry_portfolio_risk(
            request(
                "AAPL",
                asset_type=AssetType.OPTION,
                opening_cost="11",
            ),
            (
                position(
                    "AAPL",
                    asset_type=AssetType.OPTION,
                    opening_cost="10",
                ),
                position(
                    "MSFT",
                    opening_cost="10",
                ),
            ),
        )

        self.assertEqual(
            decision.reasons,
            frozenset(
                {
                    EntryRiskReason
                    .OPENING_COST_TOO_LARGE,
                    EntryRiskReason
                    .MAX_OPEN_POSITIONS_REACHED,
                    EntryRiskReason
                    .MAX_OPTION_POSITIONS_REACHED,
                    EntryRiskReason
                    .TOTAL_OPENING_COST_EXCEEDED,
                    EntryRiskReason
                    .DUPLICATE_UNDERLYING,
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()