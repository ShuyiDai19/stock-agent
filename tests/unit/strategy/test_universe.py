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

    def test_selects_top_n_by_average_volume(
        self,
    ) -> None:
        policy = (
            EquityUniverseScreeningPolicy(
                min_average_volume_30d=(
                    Decimal("1000000")
                ),
                min_market_cap=(
                    Decimal("1000000000")
                ),
                max_intraday_candidates=2,
            )
        )

        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL",
                        average_volume_30d=(
                            "5000000"
                        ),
                    ),
                    snapshot(
                        "MSFT",
                        average_volume_30d=(
                            "9000000"
                        ),
                    ),
                    snapshot(
                        "NVDA",
                        average_volume_30d=(
                            "7000000"
                        ),
                    ),
                ),
                policy=policy,
            )
        )

        self.assertEqual(
            result.eligible_symbols,
            (
                "AAPL",
                "MSFT",
                "NVDA",
            ),
        )

        self.assertEqual(
            result.selected_symbols,
            (
                "MSFT",
                "NVDA",
            ),
        )

        self.assertEqual(
            [
                item.symbol
                for item
                in result.deferred_items
            ],
            [
                "AAPL",
            ],
        )

    def test_market_cap_breaks_volume_tie(
        self,
    ) -> None:
        policy = (
            EquityUniverseScreeningPolicy(
                min_average_volume_30d=(
                    Decimal("0")
                ),
                min_market_cap=(
                    Decimal("0")
                ),
                max_intraday_candidates=2,
            )
        )

        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "AAPL",
                        average_volume_30d=(
                            "5000000"
                        ),
                        market_cap=(
                            "10000000000"
                        ),
                    ),
                    snapshot(
                        "MSFT",
                        average_volume_30d=(
                            "5000000"
                        ),
                        market_cap=(
                            "30000000000"
                        ),
                    ),
                    snapshot(
                        "NVDA",
                        average_volume_30d=(
                            "5000000"
                        ),
                        market_cap=(
                            "20000000000"
                        ),
                    ),
                ),
                policy=policy,
            )
        )

        self.assertEqual(
            result.selected_symbols,
            (
                "MSFT",
                "NVDA",
            ),
        )

    def test_symbol_breaks_complete_ranking_tie(
        self,
    ) -> None:
        policy = (
            EquityUniverseScreeningPolicy(
                min_average_volume_30d=(
                    Decimal("0")
                ),
                min_market_cap=(
                    Decimal("0")
                ),
                max_intraday_candidates=2,
            )
        )

        result = (
            screen_equity_universe(
                (
                    snapshot(
                        "NVDA"
                    ),
                    snapshot(
                        "MSFT"
                    ),
                    snapshot(
                        "AAPL"
                    ),
                ),
                policy=policy,
            )
        )

        self.assertEqual(
            result.selected_symbols,
            (
                "AAPL",
                "MSFT",
            ),
        )

    def test_rejects_nonpositive_max_intraday_candidates(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "greater than zero",
        ):
            EquityUniverseScreeningPolicy(
                min_average_volume_30d=(
                    Decimal("0")
                ),
                min_market_cap=(
                    Decimal("0")
                ),
                max_intraday_candidates=0,
            )


    def test_rejects_boolean_max_intraday_candidates(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must be an integer",
        ):
            EquityUniverseScreeningPolicy(
                min_average_volume_30d=(
                    Decimal("0")
                ),
                min_market_cap=(
                    Decimal("0")
                ),
                max_intraday_candidates=True,
            )


if __name__ == "__main__":
    unittest.main()