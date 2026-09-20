import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.domain import (
    AssetType,
)
from stock_agent.risk.entry_portfolio import (
    OpenPositionRiskSnapshot,
)
from stock_agent.orchestration.robinhood_strategy_cycle import (
    RobinhoodEquityCycleRunStatus,
    run_robinhood_equity_strategy_cycle,
    run_robinhood_equity_strategy_cycle_from_store,
)
from stock_agent.strategy.market_session import (
    RegularMarketSessionStatus,
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
                            "102.50"
                        ),
                        "venue_last_trade_time": (
                            "2026-09-18"
                            "T13:46:59Z"
                        ),
                        "bid_price": (
                            "102.45"
                        ),
                        "venue_bid_time": (
                            "2026-09-18"
                            "T13:46:58Z"
                        ),
                        "ask_price": (
                            "102.55"
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


def approved_review_payload(
    symbol: str,
    dollar_amount: str,
) -> dict:
    return {
        "data": {
            "symbol": symbol,
            "side": "buy",
            "type": "market",
            "dollar_amount": (
                dollar_amount
            ),
            "order_checks": {},
            "quote_data": {
                "bid_price": "102.45",
                "ask_price": "102.55",
                "venue_bid_time": (
                    "2026-09-18"
                    "T13:46:58Z"
                ),
                "venue_ask_time": (
                    "2026-09-18"
                    "T13:46:59Z"
                ),
            },
        }
    }


class FakeInvoker:
    def __init__(
        self,
        *,
        failing_market_data_symbols=None,
        failing_review_symbols=None,
    ) -> None:
        self.failing_market_data_symbols = set(
            failing_market_data_symbols
            or ()
        )

        self.failing_review_symbols = set(
            failing_review_symbols
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

        if (
            tool_name
            == "get_equity_quotes"
        ):
            symbol = arguments[
                "symbols"
            ][0]

            return quote_payload(
                symbol
            )

        if (
            tool_name
            == "get_equity_historicals"
        ):
            symbol = arguments[
                "symbols"
            ][0]

            if (
                symbol
                in self
                .failing_market_data_symbols
            ):
                raise RuntimeError(
                    "historicals unavailable"
                )

            return historical_payload(
                symbol
            )

        if (
            tool_name
            == "review_equity_order"
        ):
            symbol = arguments[
                "symbol"
            ]

            if (
                symbol
                in self
                .failing_review_symbols
            ):
                raise RuntimeError(
                    "review unavailable"
                )

            return approved_review_payload(
                symbol,
                arguments[
                    "dollar_amount"
                ],
            )

        raise AssertionError(
            f"unexpected tool: {tool_name}"
        )


class RobinhoodStrategyCycleTests(
    unittest.TestCase
):
    def test_runs_market_data_through_review_cycle(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_robinhood_equity_strategy_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                symbols=(
                    "AAPL",
                ),
                open_positions=(),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.loaded_candidate_count,
            1,
        )

        self.assertEqual(
            result.eligible_entry_count,
            1,
        )

        self.assertEqual(
            result.market_data_error_count,
            0,
        )

        self.assertEqual(
            result.review_error_count,
            0,
        )

        self.assertEqual(
            result.eligible_entries[
                0
            ].symbol,
            "AAPL",
        )

        self.assertEqual(
            [
                call[0]
                for call in invoker.calls
            ],
            [
                "get_equity_quotes",
                "get_equity_historicals",
                "review_equity_order",
            ],
        )

    def test_market_data_failure_does_not_block_other_symbol(
        self,
    ) -> None:
        invoker = FakeInvoker(
            failing_market_data_symbols={
                "MSFT"
            }
        )

        result = (
            run_robinhood_equity_strategy_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                symbols=(
                    "MSFT",
                    "AAPL",
                ),
                open_positions=(),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.loaded_candidate_count,
            1,
        )

        self.assertEqual(
            result.market_data_error_count,
            1,
        )

        self.assertEqual(
            result.market_data_errors[
                0
            ].symbol,
            "MSFT",
        )

        self.assertEqual(
            result.eligible_entry_count,
            1,
        )

        self.assertEqual(
            result.eligible_entries[
                0
            ].symbol,
            "AAPL",
        )

    def test_review_failure_is_reported_separately(
        self,
    ) -> None:
        invoker = FakeInvoker(
            failing_review_symbols={
                "AAPL"
            }
        )

        result = (
            run_robinhood_equity_strategy_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                symbols=(
                    "AAPL",
                ),
                open_positions=(),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.loaded_candidate_count,
            1,
        )

        self.assertEqual(
            result.market_data_error_count,
            0,
        )

        self.assertEqual(
            result.review_error_count,
            1,
        )

        self.assertEqual(
            result.eligible_entry_count,
            0,
        )

        self.assertEqual(
            result.review_errors[
                0
            ].symbol,
            "AAPL",
        )

    def test_existing_position_still_limits_capacity(
        self,
    ) -> None:
        invoker = FakeInvoker()

        existing = (
            OpenPositionRiskSnapshot(
                symbol="GOOG",
                asset_type=(
                    AssetType.EQUITY
                ),
                opening_cost=Decimal(
                    "8"
                ),
            )
        )

        result = (
            run_robinhood_equity_strategy_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                symbols=(
                    "AAPL",
                    "MSFT",
                ),
                open_positions=(
                    existing,
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
            result.loaded_candidate_count,
            2,
        )

        # Portfolio policy permits only one
        # additional position.
        self.assertEqual(
            result.eligible_entry_count,
            1,
        )

        # Same market data means same score,
        # so deterministic symbol tie-break wins.
        self.assertEqual(
            result.eligible_entries[
                0
            ].symbol,
            "AAPL",
        )

        review_calls = [
            call
            for call in invoker.calls
            if (
                call[0]
                == "review_equity_order"
            )
        ]

        self.assertEqual(
            len(review_calls),
            1,
        )

    def test_empty_universe_is_valid(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_robinhood_equity_strategy_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                symbols=(),
                open_positions=(),
                session_start=(
                    _SESSION_START
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.loaded_candidate_count,
            0,
        )

        self.assertEqual(
            result.eligible_entry_count,
            0,
        )

        self.assertEqual(
            result.market_data_error_count,
            0,
        )

        self.assertEqual(
            result.review_error_count,
            0,
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_store_position_is_used_for_portfolio_risk(
        self,
    ) -> None:
        from stock_agent.orchestration.robinhood_strategy_cycle import (
            run_robinhood_equity_strategy_cycle_from_store,
        )
        from stock_agent.state import (
            PositionRuntimeState,
            PositionStateStatus,
        )

        existing = (
            PositionRuntimeState(
                position_id=(
                    "agentic-account:"
                    "equity:AAPL:"
                    "opening-order-1"
                ),
                account_number=(
                    "agentic-account"
                ),
                asset_type=(
                    AssetType.EQUITY
                ),
                symbol="AAPL",
                opening_order_id=(
                    "opening-order-1"
                ),
                entry_price=Decimal(
                    "100"
                ),
                remaining_quantity=Decimal(
                    "0.05"
                ),
                opened_at=(
                    _SESSION_START
                ),
                highest_executable_bid=Decimal(
                    "100"
                ),
                trailing_armed=False,
                trailing_armed_at=None,
                activation_gain_ratio=Decimal(
                    "0.04"
                ),
                drawdown_ratio=Decimal(
                    "0.02"
                ),
                last_quote_at=(
                    _SESSION_START
                ),
                last_reconciled_at=(
                    _SESSION_START
                ),
                status=(
                    PositionStateStatus.ACTIVE
                ),
            )
        )

        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                if (
                    account_number
                    == "agentic-account"
                    and existing.status
                    in statuses
                ):
                    return [
                        existing
                    ]

                return []

        invoker = FakeInvoker()

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                invoker,
                Store(),
                account_number="agentic-account",
                symbols=("AAPL",),
                evaluated_at=_EVALUATED_AT,
            )
        )

        self.assertEqual(
            result.loaded_candidate_count,
            1,
        )

        self.assertEqual(
            result.eligible_entry_count,
            0,
        )

        review_calls = [
            call
            for call in invoker.calls
            if (
                call[0]
                == "review_equity_order"
            )
        ]

        self.assertEqual(
            review_calls,
            [],
        )

    def test_weekend_returns_no_trade_without_any_reads(
        self,
    ) -> None:
        class Store:
            def __init__(
                self,
            ) -> None:
                self.calls = 0

            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                self.calls += 1

                raise AssertionError(
                    "store must not be read "
                    "outside regular session"
                )

        invoker = FakeInvoker()
        store = Store()

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                invoker,
                store,
                account_number=(
                    "agentic-account"
                ),
                symbols=(
                    "AAPL",
                    "MSFT",
                ),
                evaluated_at=(
                    datetime(
                        2026,
                        9,
                        19,
                        14,
                        0,
                        tzinfo=timezone.utc,
                    )
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityCycleRunStatus
            .NO_TRADE,
        )

        self.assertEqual(
            result.session.status,
            RegularMarketSessionStatus
            .NO_SESSION,
        )

        self.assertEqual(
            result.eligible_entry_count,
            0,
        )

        self.assertEqual(
            store.calls,
            0,
        )

        self.assertEqual(
            invoker.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()