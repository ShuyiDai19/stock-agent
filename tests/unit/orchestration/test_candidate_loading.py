import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal


from stock_agent.orchestration.candidate_loading import (
    load_robinhood_equity_review_candidates,
)


_SESSION_START = datetime(
    2026,
    9,
    18,
    13,
    30,
    tzinfo=timezone.utc,
)

_EVALUATED_AT = datetime(
    2026,
    9,
    18,
    13,
    47,
    tzinfo=timezone.utc,
)


def quote_payload(
    symbol: str,
) -> dict:
    return {
        "data": {
            "results": [
                {
                    "quote": {
                        "symbol": symbol,
                        "last_trade_price": (
                            "101.20"
                        ),
                        "venue_last_trade_time": (
                            "2026-09-18"
                            "T13:46:59Z"
                        ),
                        "bid_price": (
                            "101.18"
                        ),
                        "venue_bid_time": (
                            "2026-09-18"
                            "T13:46:58Z"
                        ),
                        "ask_price": (
                            "101.22"
                        ),
                        "venue_ask_time": (
                            "2026-09-18"
                            "T13:46:59Z"
                        ),
                        "has_traded": True,
                        "state": "active",
                    }
                }
            ]
        }
    }


def historical_payload(
    symbol: str,
) -> dict:
    return {
        "data": {
            "results": [
                {
                    "symbol": symbol,
                    "interval": "5minute",
                    "bounds": "regular",
                    "bars": [
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:30:00Z"
                            ),
                            "open_price": "100",
                            "high_price": "101",
                            "low_price": "99",
                            "close_price": "100",
                            "volume": 100,
                        },
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:35:00Z"
                            ),
                            "open_price": "100",
                            "high_price": "102",
                            "low_price": "100",
                            "close_price": "101",
                            "volume": 200,
                        },
                        {
                            "begins_at": (
                                "2026-09-18"
                                "T13:40:00Z"
                            ),
                            "open_price": "101",
                            "high_price": "103",
                            "low_price": "101",
                            "close_price": "102",
                            "volume": 300,
                        },
                    ],
                }
            ]
        }
    }


class FakeInvoker:
    def __init__(
        self,
        *,
        failing_historical_symbols=None,
    ) -> None:
        self.failing_historical_symbols = set(
            failing_historical_symbols
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

        symbol = arguments[
            "symbols"
        ][0]

        if (
            tool_name
            == "get_equity_quotes"
        ):
            return quote_payload(
                symbol
            )

        if (
            tool_name
            == "get_equity_historicals"
        ):
            if (
                symbol
                in self.failing_historical_symbols
            ):
                raise RuntimeError(
                    "historicals unavailable"
                )

            return historical_payload(
                symbol
            )

        raise AssertionError(
            f"unexpected tool: {tool_name}"
        )


class CandidateLoadingTests(
    unittest.TestCase
):
    def test_loads_multiple_candidates(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            load_robinhood_equity_review_candidates(
                invoker,
                symbols=(
                    "AAPL",
                    "MSFT",
                    "NVDA",
                ),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.candidate_count,
            3,
        )

        self.assertEqual(
            result.error_count,
            0,
        )

        self.assertEqual(
            [
                candidate.symbol
                for candidate
                in result.candidates
            ],
            [
                "AAPL",
                "MSFT",
                "NVDA",
            ],
        )

        # Two read calls per symbol.
        self.assertEqual(
            len(invoker.calls),
            6,
        )

    def test_one_symbol_failure_does_not_abort_batch(
        self,
    ) -> None:
        invoker = FakeInvoker(
            failing_historical_symbols={
                "MSFT"
            }
        )

        result = (
            load_robinhood_equity_review_candidates(
                invoker,
                symbols=(
                    "AAPL",
                    "MSFT",
                    "NVDA",
                ),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            [
                candidate.symbol
                for candidate
                in result.candidates
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

        self.assertIsInstance(
            result.errors[
                0
            ].error,
            RuntimeError,
        )

    def test_preserves_custom_budget(
        self,
    ) -> None:
        result = (
            load_robinhood_equity_review_candidates(
                FakeInvoker(),
                symbols=(
                    "AAPL",
                ),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                budget=Decimal(
                    "10"
                ),
            )
        )

        self.assertEqual(
            result.candidates[
                0
            ].request.opening_cost,
            Decimal("10"),
        )

    def test_rejects_duplicate_symbols_before_broker_calls(
        self,
    ) -> None:
        invoker = FakeInvoker()

        with self.assertRaisesRegex(
            ValueError,
            "duplicates",
        ):
            load_robinhood_equity_review_candidates(
                invoker,
                symbols=(
                    "AAPL",
                    "AAPL",
                ),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_empty_symbol_set_is_valid(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            load_robinhood_equity_review_candidates(
                invoker,
                symbols=(),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.candidates,
            (),
        )

        self.assertEqual(
            result.errors,
            (),
        )

        self.assertEqual(
            invoker.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()