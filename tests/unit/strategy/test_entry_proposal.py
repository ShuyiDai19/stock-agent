import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.domain import AssetType
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_decision import (
    evaluate_entry_decision,
)
from stock_agent.strategy.entry_proposal import (
    EntryProposalError,
    build_equity_entry_proposal,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def make_market(
    *,
    price: str = "200",
) -> BullishEntrySnapshot:
    return BullishEntrySnapshot(
        symbol="AAPL",
        price=Decimal(price),
        session_open=Decimal("195"),
        vwap=Decimal("198"),
        recent_5m_closes=(
            Decimal("197"),
            Decimal("199"),
            Decimal("200"),
        ),
        observed_at=_NOW,
    )


def make_request(
    *,
    asset_type: AssetType = AssetType.EQUITY,
    opening_cost: str = "8",
) -> EntryRiskRequest:
    return EntryRiskRequest(
        symbol="AAPL",
        asset_type=asset_type,
        opening_cost=Decimal(
            opening_cost
        ),
    )


class EquityEntryProposalTests(
    unittest.TestCase
):
    def test_builds_proposal_from_approved_decision(
        self,
    ) -> None:
        market = make_market()
        request = make_request()

        decision = evaluate_entry_decision(
            market=market,
            request=request,
            open_positions=(),
        )

        proposal = (
            build_equity_entry_proposal(
                market=market,
                request=request,
                decision=decision,
            )
        )

        self.assertEqual(
            proposal.symbol,
            "AAPL",
        )

        self.assertEqual(
            proposal.budget,
            Decimal("8"),
        )

        self.assertEqual(
            proposal.reference_price,
            Decimal("200"),
        )

        self.assertEqual(
            proposal.estimated_quantity,
            Decimal("0.04"),
        )

        self.assertEqual(
            proposal.proposed_at,
            _NOW,
        )

    def test_uses_requested_budget_for_sizing(
        self,
    ) -> None:
        market = make_market(
            price="250"
        )

        request = make_request(
            opening_cost="10"
        )

        decision = evaluate_entry_decision(
            market=market,
            request=request,
            open_positions=(),
        )

        proposal = (
            build_equity_entry_proposal(
                market=market,
                request=request,
                decision=decision,
            )
        )

        self.assertEqual(
            proposal.estimated_quantity,
            Decimal("0.04"),
        )

    def test_rejects_failed_entry_decision(
        self,
    ) -> None:
        market = BullishEntrySnapshot(
            symbol="AAPL",
            price=Decimal("190"),
            session_open=Decimal("195"),
            vwap=Decimal("198"),
            recent_5m_closes=(
                Decimal("200"),
                Decimal("195"),
                Decimal("190"),
            ),
            observed_at=_NOW,
        )

        request = make_request()

        decision = evaluate_entry_decision(
            market=market,
            request=request,
            open_positions=(),
        )

        self.assertFalse(
            decision.approved
        )

        with self.assertRaisesRegex(
            EntryProposalError,
            "decision must be approved",
        ):
            build_equity_entry_proposal(
                market=market,
                request=request,
                decision=decision,
            )

    def test_rejects_option_request(
        self,
    ) -> None:
        market = make_market()

        request = make_request(
            asset_type=AssetType.OPTION
        )

        decision = evaluate_entry_decision(
            market=market,
            request=request,
            open_positions=(),
        )

        self.assertTrue(
            decision.approved
        )

        with self.assertRaisesRegex(
            EntryProposalError,
            "requires an equity request",
        ):
            build_equity_entry_proposal(
                market=market,
                request=request,
                decision=decision,
            )


if __name__ == "__main__":
    unittest.main()