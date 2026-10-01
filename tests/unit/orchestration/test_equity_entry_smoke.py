import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal
from unittest.mock import patch

from stock_agent.orchestration.equity_entry_smoke import (
    build_deterministic_equity_smoke_loader,
)
from stock_agent.strategy.candidate_generation import (
    EquityCandidateMarketData,
)


_NOW = datetime(
    2026,
    10,
    1,
    16,
    0,
    tzinfo=timezone.utc,
)

_SESSION_START = datetime(
    2026,
    10,
    1,
    13,
    30,
    tzinfo=timezone.utc,
)


class EquityEntrySmokeTests(
    unittest.TestCase
):
    def test_preserves_real_execution_quote_but_forces_confirmation(
        self,
    ) -> None:
        real_data = (
            EquityCandidateMarketData(
                symbol="AAPL",
                price=Decimal("250"),
                session_open=Decimal(
                    "255"
                ),
                vwap=Decimal("252"),
                recent_5m_closes=(
                    Decimal("253"),
                    Decimal("252"),
                    Decimal("251"),
                ),
                bid=Decimal("249.95"),
                ask=Decimal("250.05"),
                signal_observed_at=_NOW,
                quote_observed_at=_NOW,
            )
        )

        loader = (
            build_deterministic_equity_smoke_loader(
                smoke_symbol="AAPL",
            )
        )

        with patch(
            "stock_agent.orchestration."
            "equity_entry_smoke."
            "load_robinhood_equity_candidate_market_data",
            return_value=real_data,
        ):
            result = loader(
                object(),
                symbols=(
                    "AAPL",
                ),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=_NOW,
                budget=Decimal("8"),
            )

        self.assertEqual(
            result.candidate_count,
            1,
        )

        candidate = (
            result.candidates[0]
        )

        self.assertEqual(
            candidate.market.price,
            Decimal("250"),
        )

        self.assertLess(
            candidate.market.session_open,
            candidate.market.price,
        )

        self.assertLess(
            candidate.market.vwap,
            candidate.market.price,
        )

        self.assertEqual(
            candidate.market.recent_5m_closes,
            (
                Decimal("250"),
                Decimal("250"),
                Decimal("250"),
            ),
        )

        self.assertEqual(
            candidate.execution_quote.bid,
            Decimal("249.95"),
        )

        self.assertEqual(
            candidate.execution_quote.ask,
            Decimal("250.05"),
        )

        self.assertEqual(
            candidate.execution_quote.observed_at,
            _NOW,
        )

        self.assertEqual(
            candidate.request.opening_cost,
            Decimal("8"),
        )

    def test_requires_exact_smoke_symbol(
        self,
    ) -> None:
        loader = (
            build_deterministic_equity_smoke_loader(
                smoke_symbol="AAPL",
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "exactly the configured",
        ):
            loader(
                object(),
                symbols=(
                    "AAPL",
                    "MSFT",
                ),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=_NOW,
                budget=Decimal("8"),
            )


if __name__ == "__main__":
    unittest.main()