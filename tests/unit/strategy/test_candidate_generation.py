import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal

from stock_agent.domain import (
    AssetType,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
    EquityCandidateMarketData,
    build_equity_review_candidate,
    build_equity_review_candidates,
    compute_equity_candidate_priority,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def market_data(
    symbol: str = "AAPL",
    *,
    price: str = "100",
    session_open: str = "99",
    vwap: str = "99.50",
    closes: tuple[
        str,
        str,
        str,
    ] = (
        "99",
        "99.50",
        "100",
    ),
) -> EquityCandidateMarketData:
    return EquityCandidateMarketData(
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
        bid=Decimal("99.95"),
        ask=Decimal("100.05"),
        signal_observed_at=_NOW,
        quote_observed_at=(
            _NOW
            + timedelta(seconds=1)
        ),
    )


class CandidateGenerationTests(
    unittest.TestCase
):
    def test_builds_review_candidate_from_market_data(
        self,
    ) -> None:
        candidate = (
            build_equity_review_candidate(
                market_data()
            )
        )

        self.assertEqual(
            candidate.symbol,
            "AAPL",
        )

        self.assertEqual(
            candidate.market.price,
            Decimal("100"),
        )

        self.assertEqual(
            candidate.market.vwap,
            Decimal("99.50"),
        )

        self.assertEqual(
            candidate.request.asset_type,
            AssetType.EQUITY,
        )

        self.assertEqual(
            candidate.request.opening_cost,
            DEFAULT_ENTRY_BUDGET,
        )

        self.assertEqual(
            candidate.execution_quote.bid,
            Decimal("99.95"),
        )

        self.assertEqual(
            candidate.execution_quote.ask,
            Decimal("100.05"),
        )

    def test_stronger_market_data_gets_higher_priority(
        self,
    ) -> None:
        stronger = market_data(
            price="101",
            session_open="99",
            vwap="99.50",
            closes=(
                "99",
                "100",
                "101",
            ),
        )

        weaker = market_data(
            price="100",
            session_open="99",
            vwap="99.50",
            closes=(
                "99.5",
                "99.8",
                "100",
            ),
        )

        self.assertGreater(
            compute_equity_candidate_priority(
                stronger
            ),
            compute_equity_candidate_priority(
                weaker
            ),
        )

    def test_negative_priority_is_allowed(
        self,
    ) -> None:
        data = market_data(
            price="98",
            session_open="99",
            vwap="99.50",
            closes=(
                "100",
                "99",
                "98",
            ),
        )

        priority = (
            compute_equity_candidate_priority(
                data
            )
        )

        self.assertLess(
            priority,
            Decimal("0"),
        )

        candidate = (
            build_equity_review_candidate(
                data
            )
        )

        self.assertEqual(
            candidate.priority_score,
            priority,
        )

    def test_custom_budget_is_preserved(
        self,
    ) -> None:
        candidate = (
            build_equity_review_candidate(
                market_data(),
                budget=Decimal("10"),
            )
        )

        self.assertEqual(
            candidate.request.opening_cost,
            Decimal("10"),
        )

    def test_builds_multiple_candidates(
        self,
    ) -> None:
        candidates = (
            build_equity_review_candidates(
                (
                    market_data(
                        "AAPL"
                    ),
                    market_data(
                        "MSFT"
                    ),
                    market_data(
                        "NVDA"
                    ),
                )
            )
        )

        self.assertEqual(
            [
                candidate.symbol
                for candidate
                in candidates
            ],
            [
                "AAPL",
                "MSFT",
                "NVDA",
            ],
        )

    def test_rejects_inverted_quote(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ask cannot be below bid",
        ):
            EquityCandidateMarketData(
                symbol="AAPL",
                price=Decimal("100"),
                session_open=Decimal(
                    "99"
                ),
                vwap=Decimal("99.5"),
                recent_5m_closes=(
                    Decimal("99"),
                    Decimal("99.5"),
                    Decimal("100"),
                ),
                bid=Decimal("100.10"),
                ask=Decimal("100"),
                signal_observed_at=_NOW,
                quote_observed_at=_NOW,
            )


if __name__ == "__main__":
    unittest.main()