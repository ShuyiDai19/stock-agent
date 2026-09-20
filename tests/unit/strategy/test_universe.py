import unittest
from decimal import Decimal

from stock_agent.strategy.universe import (
    EquityUniverseRejectReason,
    EquityUniverseScreeningPolicy,
    EquityUniverseSnapshot,
    screen_equity_universe,
)


_POLICY = EquityUniverseScreeningPolicy(
    min_average_volume_30d=Decimal(
        "1000000"
    ),
    min_market_cap=Decimal(
        "1000000000"
    ),
)


def snapshot(
    symbol: str,
    *,
    average_volume_30d: str = (
        "5000000"
    ),
    market_cap: str = (
        "10000000000"
    ),
) -> EquityUniverseSnapshot:
    return EquityUniverseSnapshot(
        symbol=symbol,
        average_volume_30d=Decimal(
            average_volume_30d
        ),
        market_cap=Decimal(
            market_cap
        ),
    )


class EquityUniverseTests(
    unittest.TestCase
):
    def test_eligible_symbol_passes(
        self,
    ) -> None:
        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL"
                    ),
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.eligible_symbols,
            (
                "AAPL",
            ),
        )

        self.assertEqual(
            result.rejected_items,
            (),
        )

    def test_low_volume_is_rejected(
        self,
    ) -> None:
        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL",
                        average_volume_30d=(
                            "999999"
                        ),
                    ),
                ),
                policy=_POLICY,
            )
        )

        item = result.items[0]

        self.assertFalse(
            item.eligible
        )

        self.assertEqual(
            item.reasons,
            frozenset(
                {
                    EquityUniverseRejectReason
                    .BELOW_MIN_AVERAGE_VOLUME
                }
            ),
        )

    def test_low_market_cap_is_rejected(
        self,
    ) -> None:
        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL",
                        market_cap=(
                            "999999999"
                        ),
                    ),
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.items[0].reasons,
            frozenset(
                {
                    EquityUniverseRejectReason
                    .BELOW_MIN_MARKET_CAP
                }
            ),
        )

    def test_symbol_can_have_multiple_rejection_reasons(
        self,
    ) -> None:
        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL",
                        average_volume_30d=(
                            "100"
                        ),
                        market_cap="100",
                    ),
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.items[0].reasons,
            frozenset(
                {
                    EquityUniverseRejectReason
                    .BELOW_MIN_AVERAGE_VOLUME,
                    EquityUniverseRejectReason
                    .BELOW_MIN_MARKET_CAP,
                }
            ),
        )

    def test_threshold_values_are_eligible(
        self,
    ) -> None:
        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL",
                        average_volume_30d=(
                            "1000000"
                        ),
                        market_cap=(
                            "1000000000"
                        ),
                    ),
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.eligible_symbols,
            (
                "AAPL",
            ),
        )

    def test_preserves_input_order(
        self,
    ) -> None:
        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "NVDA"
                    ),
                    snapshot(
                        "AAPL"
                    ),
                    snapshot(
                        "MSFT",
                        market_cap="100",
                    ),
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.eligible_symbols,
            (
                "NVDA",
                "AAPL",
            ),
        )

        self.assertEqual(
            [
                item.symbol
                for item
                in result.rejected_items
            ],
            [
                "MSFT",
            ],
        )

    def test_duplicate_symbol_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "duplicate symbols",
        ):
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL"
                    ),
                    snapshot(
                        "AAPL"
                    ),
                ),
                policy=_POLICY,
            )


if __name__ == "__main__":
    unittest.main()