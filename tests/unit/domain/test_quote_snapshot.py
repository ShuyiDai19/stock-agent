import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.domain import QuoteSnapshot


class QuoteSnapshotTests(unittest.TestCase):
    def test_creates_valid_quote_snapshot(self) -> None:
        observed_at = datetime(
            2026,
            8,
            11,
            14,
            5,
            tzinfo=timezone.utc,
        )

        quote = QuoteSnapshot(
            symbol="AAPL",
            bid=Decimal("103.25"),
            observed_at=observed_at,
        )

        self.assertEqual(
            quote.symbol,
            "AAPL",
        )
        self.assertEqual(
            quote.bid,
            Decimal("103.25"),
        )
        self.assertEqual(
            quote.observed_at,
            observed_at,
        )

    def test_rejects_empty_symbol(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "symbol cannot be empty",
        ):
            QuoteSnapshot(
                symbol="   ",
                bid=Decimal("103.25"),
                observed_at=datetime.now(timezone.utc),
            )

    def test_rejects_non_positive_bid(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "bid must be greater than zero",
        ):
            QuoteSnapshot(
                symbol="AAPL",
                bid=Decimal("0"),
                observed_at=datetime.now(timezone.utc),
            )

    def test_rejects_non_finite_bid(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "bid must be finite",
        ):
            QuoteSnapshot(
                symbol="AAPL",
                bid=Decimal("NaN"),
                observed_at=datetime.now(timezone.utc),
            )

    def test_rejects_naive_observed_at(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "observed_at must be timezone-aware",
        ):
            QuoteSnapshot(
                symbol="AAPL",
                bid=Decimal("103.25"),
                observed_at=datetime(
                    2026,
                    8,
                    11,
                    14,
                    5,
                ),
            )


if __name__ == "__main__":
    unittest.main()