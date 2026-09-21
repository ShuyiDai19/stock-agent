import unittest
from decimal import Decimal

from stock_agent.orchestration.robinhood_universe import (
    RobinhoodUniverseSymbolNotFoundError,
    load_and_screen_robinhood_equity_universe,
    load_robinhood_equity_universe,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)


_POLICY = EquityUniverseScreeningPolicy(
    min_average_volume_30d=Decimal(
        "1000000"
    ),
    min_market_cap=Decimal(
        "1000000000"
    ),
)


def fundamental(
    symbol: str,
    *,
    average_volume_30d: str = (
        "5000000"
    ),
    market_cap: str = (
        "10000000000"
    ),
) -> dict:
    return {
        "symbol": symbol,
        "average_volume_30_days": (
            average_volume_30d
        ),
        "market_cap": (
            market_cap
        ),
    }


class FakeInvoker:
    def __init__(
        self,
        *,
        not_found=None,
        low_volume=None,
        low_market_cap=None,
        malformed=None,
        failing_call_numbers=None,
    ) -> None:
        self.not_found = set(
            not_found or ()
        )

        self.low_volume = set(
            low_volume or ()
        )

        self.low_market_cap = set(
            low_market_cap or ()
        )

        self.malformed = set(
            malformed or ()
        )

        self.failing_call_numbers = set(
            failing_call_numbers
            or ()
        )

        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        call_number = len(
            self.calls
        )

        if (
            call_number
            in self.failing_call_numbers
        ):
            raise RuntimeError(
                "fundamentals unavailable"
            )

        self.assert_tool(
            tool_name
        )

        symbols = arguments[
            "symbols"
        ]

        results = []
        not_found = []

        for symbol in symbols:
            if (
                symbol
                in self.not_found
            ):
                not_found.append(
                    symbol
                )

                continue

            item = fundamental(
                symbol,
                average_volume_30d=(
                    "100"
                    if symbol
                    in self.low_volume
                    else "5000000"
                ),
                market_cap=(
                    "100"
                    if symbol
                    in self.low_market_cap
                    else "10000000000"
                ),
            )

            if symbol in self.malformed:
                item[
                    "market_cap"
                ] = None

            results.append(
                item
            )

        return {
            "data": {
                "results": results,
                "not_found": (
                    not_found
                ),
            }
        }

    @staticmethod
    def assert_tool(
        tool_name,
    ) -> None:
        if (
            tool_name
            != "get_equity_fundamentals"
        ):
            raise AssertionError(
                f"unexpected tool: "
                f"{tool_name}"
            )


class RobinhoodUniverseTests(
    unittest.TestCase
):
    def test_loads_and_screens_symbols(
        self,
    ) -> None:
        invoker = FakeInvoker(
            low_volume={
                "MSFT"
            }
        )

        result = (
            load_and_screen_robinhood_equity_universe(
                invoker,
                symbols=(
                    "AAPL",
                    "MSFT",
                    "NVDA",
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.eligible_symbols,
            (
                "AAPL",
                "NVDA",
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

        self.assertEqual(
            result.load_errors,
            (),
        )

    def test_batches_at_ten_symbols(
        self,
    ) -> None:
        symbols = tuple(
            f"SYM{index}"
            for index in range(
                12
            )
        )

        invoker = FakeInvoker()

        result = (
            load_robinhood_equity_universe(
                invoker,
                symbols=symbols,
            )
        )

        self.assertEqual(
            result.snapshot_count,
            12,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertEqual(
            len(
                invoker.calls[
                    0
                ][1]["symbols"]
            ),
            10,
        )

        self.assertEqual(
            len(
                invoker.calls[
                    1
                ][1]["symbols"]
            ),
            2,
        )

        self.assertEqual(
            invoker.calls[
                0
            ][1]["bounds"],
            "regular",
        )

    def test_not_found_is_explicit_error(
        self,
    ) -> None:
        invoker = FakeInvoker(
            not_found={
                "MSFT"
            }
        )

        result = (
            load_robinhood_equity_universe(
                invoker,
                symbols=(
                    "AAPL",
                    "MSFT",
                ),
            )
        )

        self.assertEqual(
            [
                snapshot.symbol
                for snapshot
                in result.snapshots
            ],
            [
                "AAPL",
            ],
        )

        self.assertEqual(
            result.error_count,
            1,
        )

        self.assertEqual(
            result.errors[
                0
            ].symbol,
            "MSFT",
        )

        self.assertIsInstance(
            result.errors[
                0
            ].error,
            RobinhoodUniverseSymbolNotFoundError,
        )

    def test_malformed_symbol_does_not_drop_good_symbol(
        self,
    ) -> None:
        invoker = FakeInvoker(
            malformed={
                "MSFT"
            }
        )

        result = (
            load_robinhood_equity_universe(
                invoker,
                symbols=(
                    "AAPL",
                    "MSFT",
                    "NVDA",
                ),
            )
        )

        self.assertEqual(
            [
                snapshot.symbol
                for snapshot
                in result.snapshots
            ],
            [
                "AAPL",
                "NVDA",
            ],
        )

        self.assertEqual(
            result.error_count,
            1,
        )

        self.assertEqual(
            result.errors[
                0
            ].symbol,
            "MSFT",
        )

    def test_failed_batch_does_not_block_next_batch(
        self,
    ) -> None:
        symbols = tuple(
            f"SYM{index}"
            for index in range(
                12
            )
        )

        invoker = FakeInvoker(
            failing_call_numbers={
                1
            }
        )

        result = (
            load_robinhood_equity_universe(
                invoker,
                symbols=symbols,
            )
        )

        self.assertEqual(
            result.error_count,
            10,
        )

        self.assertEqual(
            [
                snapshot.symbol
                for snapshot
                in result.snapshots
            ],
            [
                "SYM10",
                "SYM11",
            ],
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_preserves_requested_symbol_order(
        self,
    ) -> None:
        result = (
            load_and_screen_robinhood_equity_universe(
                FakeInvoker(),
                symbols=(
                    "NVDA",
                    "AAPL",
                    "MSFT",
                ),
                policy=_POLICY,
            )
        )

        self.assertEqual(
            result.eligible_symbols,
            (
                "NVDA",
                "AAPL",
                "MSFT",
            ),
        )

    def test_duplicate_symbols_fail_before_broker_call(
        self,
    ) -> None:
        invoker = FakeInvoker()

        with self.assertRaisesRegex(
            ValueError,
            "duplicates",
        ):
            load_robinhood_equity_universe(
                invoker,
                symbols=(
                    "AAPL",
                    "AAPL",
                ),
            )

        self.assertEqual(
            invoker.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()