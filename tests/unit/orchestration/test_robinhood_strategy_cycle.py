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
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)
from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
    EquityEntryPlacementStatus,
)
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightBlocker,
    EquityEntryPreflightSnapshot,
)
from stock_agent.orchestration.equity_entry_preflight_service import (
    EquityEntryPreflightBlockedError,
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

_LIVE_EVALUATED_AT = datetime(
    2026,
    9,
    18,
    14,
    17,
    tzinfo=timezone.utc,
)

_UNIVERSE_POLICY = (
    EquityUniverseScreeningPolicy(
        min_average_volume_30d=Decimal(
            "1000000"
        ),
        min_market_cap=Decimal(
            "1000000000"
        ),
    )
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

class NoopEntryRecoveryService:
    def __init__(self) -> None:
        self.calls = []

    def recover(
        self,
        *,
        account_number: str,
    ):
        self.calls.append(
            account_number
        )
        return []

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
            == "get_equity_fundamentals"
        ):
            symbols = arguments[
                "symbols"
            ]

            return {
                "data": {
                    "results": [
                        {
                            "symbol": symbol,
                            "average_volume_30_days": (
                                "5000000"
                            ),
                            "market_cap": (
                                "10000000000"
                            ),
                        }
                        for symbol in symbols
                    ],
                    "not_found": [],
                }
            }


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

class LiveFakeInvoker(
    FakeInvoker
):
    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        if (
            tool_name
            == "get_equity_quotes"
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
                                    "T14:16:59Z"
                                ),
                                "bid_price": (
                                    "102.45"
                                ),
                                "venue_bid_time": (
                                    "2026-09-18"
                                    "T14:16:58Z"
                                ),
                                "ask_price": (
                                    "102.55"
                                ),
                                "venue_ask_time": (
                                    "2026-09-18"
                                    "T14:16:59Z"
                                ),
                                "has_traded": True,
                                "state": "active",
                            }
                        }
                    ]
                }
            }

        if (
            tool_name
            == "get_equity_historicals"
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
                                        "T14:00:00Z"
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
                                        "T14:05:00Z"
                                    ),
                                    "open_price": "101",
                                    "high_price": "103",
                                    "low_price": "101",
                                    "close_price": "102",
                                    "volume": 300,
                                },
                                {
                                    "begins_at": (
                                        "2026-09-18"
                                        "T14:10:00Z"
                                    ),
                                    "open_price": "102",
                                    "high_price": "103",
                                    "low_price": "101",
                                    "close_price": "102.5",
                                    "volume": 300,
                                },
                            ],
                        }
                    ]
                }
            }

        if (
            tool_name
            == "review_equity_order"
        ):
            self.calls.append(
                (
                    tool_name,
                    dict(arguments),
                )
            )

            symbol = arguments[
                "symbol"
            ]

            return {
                "data": {
                    "symbol": symbol,
                    "side": "buy",
                    "type": "market",
                    "dollar_amount": (
                        arguments[
                            "dollar_amount"
                        ]
                    ),
                    "order_checks": {},
                    "quote_data": {
                        "bid_price": (
                            "102.45"
                        ),
                        "ask_price": (
                            "102.55"
                        ),
                        "venue_bid_time": (
                            "2026-09-18"
                            "T14:16:58Z"
                        ),
                        "venue_ask_time": (
                            "2026-09-18"
                            "T14:16:59Z"
                        ),
                    },
                }
            }

        return super().call_tool(
            tool_name,
            arguments,
        )

class ExplodingPlacer:
    def place(
        self,
        item,
        *,
        account_number,
        attempted_at,
    ):
        raise AssertionError(
            "default REVIEW_ONLY mode "
            "must not call placer"
        )

class RecordingPlacer:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def place(
        self,
        item,
        *,
        account_number,
        attempted_at,
    ):
        from stock_agent.brokers.robinhood.entry_placement import (
            RobinhoodEquityEntryPlacementResult,
        )

        self.calls.append(
            (
                item.symbol,
                account_number,
                attempted_at,
            )
        )

        return (
            RobinhoodEquityEntryPlacementResult(
                ref_id=(
                    f"ref-{item.symbol}"
                ),
                broker_order_id=(
                    f"order-{item.symbol}"
                ),
                submitted_at=(
                    attempted_at
                ),
            )
        )

class RecordingActivationReconciler:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def reconcile(
        self,
        *,
        account_number: str,
    ):
        self.calls.append(
            account_number
        )

        return ()

class CleanPreflightReader:
    def __init__(
        self,
        *,
        events=None,
    ) -> None:
        self.calls = []
        self.events = events

    def read(
        self,
        *,
        account_number,
        evaluated_at,
    ):
        self.calls.append(
            (
                account_number,
                evaluated_at,
            )
        )

        if self.events is not None:
            self.events.append(
                "preflight"
            )

        return EquityEntryPreflightSnapshot(
            has_existing_position=False,
            has_open_equity_order=False,
            has_open_option_order=False,
            has_opening_order_today=False,
            buying_power=Decimal("90"),
            cash=Decimal("90"),
        )

class ExistingPositionPreflightReader:
    def read(
        self,
        *,
        account_number,
        evaluated_at,
    ):
        return EquityEntryPreflightSnapshot(
            has_existing_position=True,
            has_open_equity_order=False,
            has_open_option_order=False,
            has_opening_order_today=False,
            buying_power=Decimal("90"),
            cash=Decimal("90"),
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
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
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
                allowed_symbols=(
                    "AAPL",
                    "MSFT",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
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

    def test_from_store_runs_universe_before_candidate_pipeline(
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

                return []

        invoker = FakeInvoker()
        store = Store()

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                invoker,
                store,
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityCycleRunStatus
            .RAN,
        )

        self.assertEqual(
            result.universe_eligible_symbols,
            (
                "AAPL",
            ),
        )

        self.assertEqual(
            result.universe_error_count,
            0,
        )

        self.assertEqual(
            result.universe_rejected_count,
            0,
        )

        self.assertEqual(
            store.calls,
            1,
        )

        self.assertEqual(
            [
                call[0]
                for call in invoker.calls
            ],
            [
                "get_equity_fundamentals",
                "get_equity_quotes",
                "get_equity_historicals",
                "review_equity_order",
            ],
        )

        self.assertEqual(
            result.execution_mode,
            EquityEntryExecutionMode
            .REVIEW_ONLY,
        )

        self.assertEqual(
            result.placement_count,
            0,
        )

        self.assertEqual(
            result.placement_failure_count,
            0,
        )

        self.assertEqual(
            result.placement_blocked_count,
            0,
        )

    def test_empty_screened_universe_returns_no_trade_without_candidate_reads(
        self,
    ) -> None:
        class UniverseRejectingInvoker:
            def __init__(
                self,
            ) -> None:
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
                    != "get_equity_fundamentals"
                ):
                    raise AssertionError(
                        "candidate pipeline "
                        "must not run"
                    )

                return {
                    "data": {
                        "results": [
                            {
                                "symbol": symbol,
                                "average_volume_30_days": (
                                    "100"
                                ),
                                "market_cap": (
                                    "100"
                                ),
                            }
                            for symbol
                            in arguments[
                                "symbols"
                            ]
                        ],
                        "not_found": [],
                    }
                }

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
                    "position store must not "
                    "be read when universe "
                    "is empty"
                )

        invoker = (
            UniverseRejectingInvoker()
        )

        store = Store()

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                invoker,
                store,
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                    "MSFT",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityCycleRunStatus
            .NO_TRADE,
        )

        self.assertEqual(
            result.universe_eligible_symbols,
            (),
        )

        self.assertEqual(
            result.universe_rejected_count,
            2,
        )

        self.assertEqual(
            result.universe_error_count,
            0,
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
            [
                call[0]
                for call in invoker.calls
            ],
            [
                "get_equity_fundamentals",
            ],
        )

    def test_only_selected_universe_symbols_enter_intraday_pipeline(
        self,
    ) -> None:
        class RankedUniverseInvoker(
            FakeInvoker
        ):
            def call_tool(
                self,
                tool_name,
                arguments,
            ):
                if (
                    tool_name
                    == "get_equity_fundamentals"
                ):
                    self.calls.append(
                        (
                            tool_name,
                            dict(arguments),
                        )
                    )

                    volumes = {
                        "AAPL": "5000000",
                        "MSFT": "9000000",
                        "NVDA": "7000000",
                    }

                    return {
                        "data": {
                            "results": [
                                {
                                    "symbol": symbol,
                                    "average_volume_30_days": (
                                        volumes[
                                            symbol
                                        ]
                                    ),
                                    "market_cap": (
                                        "10000000000"
                                    ),
                                }
                                for symbol
                                in arguments[
                                    "symbols"
                                ]
                            ],
                            "not_found": [],
                        }
                    }

                return super().call_tool(
                    tool_name,
                    arguments,
                )

        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                return []

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

        invoker = (
            RankedUniverseInvoker()
        )

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                invoker,
                Store(),
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                    "MSFT",
                    "NVDA",
                ),
                universe_policy=policy,
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertEqual(
            result.universe_eligible_symbols,
            (
                "AAPL",
                "MSFT",
                "NVDA",
            ),
        )

        self.assertEqual(
            result.universe_selected_symbols,
            (
                "MSFT",
                "NVDA",
            ),
        )

        self.assertEqual(
            result.universe_deferred_count,
            1,
        )

        market_data_symbols = []

        for (
            tool_name,
            arguments,
        ) in invoker.calls:
            if tool_name in {
                "get_equity_quotes",
                "get_equity_historicals",
            }:
                market_data_symbols.extend(
                    arguments[
                        "symbols"
                    ]
                )

        self.assertNotIn(
            "AAPL",
            market_data_symbols,
        )

        self.assertIn(
            "MSFT",
            market_data_symbols,
        )

        self.assertIn(
            "NVDA",
            market_data_symbols,
        )

    def test_from_store_defaults_to_review_only(
        self,
    ) -> None:
        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                return []

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                Store(),
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                placer=(
                    ExplodingPlacer()
                ),
            )
        )

        self.assertEqual(
            result.status,
            RobinhoodEquityCycleRunStatus
            .RAN,
        )

        self.assertEqual(
            result.execution_mode,
            EquityEntryExecutionMode
            .REVIEW_ONLY,
        )

        self.assertEqual(
            result.placement_count,
            0,
        )

    def test_from_store_live_mode_executes_approved_entry(
        self,
    ) -> None:
        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                return []

        placer = RecordingPlacer()

        reconciler = (
            RecordingActivationReconciler()
        )

        invoker = LiveFakeInvoker()

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                invoker,
                Store(),
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _LIVE_EVALUATED_AT
                ),
                execution_mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                placer=placer,
                activation_reconciler=(
                    reconciler
                ),
                entry_recovery_service=(
                    NoopEntryRecoveryService()
                ),
                preflight_reader=(
                    CleanPreflightReader()
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )
        )

        self.assertEqual(
            result.execution_mode,
            EquityEntryExecutionMode
            .LIVE,
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
            result.eligible_entry_count,
            1,
        )

        self.assertEqual(
            [
                call[0]
                for call
                in placer.calls
            ],
            [
                "AAPL",
            ],
        )

        self.assertEqual(
            result.placement_count,
            1,
        )

        self.assertEqual(
            result.placement_failure_count,
            0,
        )

        self.assertEqual(
            reconciler.calls,
            [
                "agentic-account",
            ],
        )

    def test_live_mode_requires_placer_for_approved_entry(
        self,
    ) -> None:
        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                return []

        with self.assertRaisesRegex(
            ValueError,
            "requires placer",
        ):
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                Store(),
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                execution_mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                entry_recovery_service=(
                    NoopEntryRecoveryService()
                ),
                activation_reconciler=(
                    RecordingActivationReconciler()
                ),
                preflight_reader=(
                    CleanPreflightReader()
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )

    def test_live_mode_requires_activation_reconciler(
        self,
    ) -> None:
        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                return []

        with self.assertRaisesRegex(
            ValueError,
            "requires activation reconciler",
        ):
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                Store(),
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
                execution_mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                entry_recovery_service=(
                    NoopEntryRecoveryService()
                ),
                placer=RecordingPlacer(),
                preflight_reader=(
                    CleanPreflightReader()
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )

    def test_live_reconciles_entry_before_loading_portfolio_risk(
        self,
    ) -> None:
        from stock_agent.state import (
            PositionRuntimeState,
            PositionStateStatus,
        )

        events = []

        activated = (
            PositionRuntimeState(
                position_id=(
                    "agentic-account:"
                    "equity:AAPL:"
                    "broker-order-1"
                ),
                account_number=(
                    "agentic-account"
                ),
                asset_type=(
                    AssetType.EQUITY
                ),
                symbol="AAPL",
                opening_order_id=(
                    "broker-order-1"
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
            def __init__(
                self,
            ) -> None:
                self.states = []

            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                events.append(
                    "load_positions"
                )

                return [
                    state
                    for state in self.states
                    if (
                        state.account_number
                        == account_number
                        and state.status
                        in statuses
                    )
                ]

        class RecoveryService:
            def recover(
                self,
                *,
                account_number,
            ):
                events.append(
                    "recover"
                )
                return []


        class ActivationReconciler:
            def __init__(
                self,
                store,
            ) -> None:
                self.store = store

            def reconcile(
                self,
                *,
                account_number,
            ):
                events.append(
                    "activate"
                )

                self.store.states.append(
                    activated
                )

                return (
                    activated,
                )

        store = Store()

        placer = RecordingPlacer()

        result = (
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                store,
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _LIVE_EVALUATED_AT
                ),
                execution_mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                entry_recovery_service=(
                    RecoveryService()
                ),
                activation_reconciler=(
                    ActivationReconciler(
                        store
                    )
                ),
                placer=placer,
                preflight_reader=(
                    CleanPreflightReader(
                        events=events
                    )
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )
        )


        self.assertEqual(
            result.eligible_entry_count,
            0,
        )

        self.assertEqual(
            placer.calls,
            [],
        )

        self.assertEqual(
            events,
            [
                "recover",
                "activate",
                "preflight",
                "load_positions",
            ],
        )

    def test_live_mode_requires_entry_recovery_service(
        self,
    ) -> None:
        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                return []

        with self.assertRaisesRegex(
            ValueError,
            "requires entry recovery service",
        ):
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                Store(),
                account_number="agentic-account",
                allowed_symbols=("AAPL",),
                universe_policy=_UNIVERSE_POLICY,
                evaluated_at=_EVALUATED_AT,
                execution_mode=(
                    EquityEntryExecutionMode.LIVE
                ),
                placer=RecordingPlacer(),
                activation_reconciler=(
                    RecordingActivationReconciler()
                ),
                preflight_reader=(
                    CleanPreflightReader()
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )

    def test_live_mode_blocks_when_entry_recovery_is_unresolved(
        self,
    ) -> None:
        events = []

        class RecoveryResult:
            recovered = False

        class RecoveryService:
            def recover(
                self,
                *,
                account_number,
            ):
                events.append(
                    "recover"
                )
                return [
                    RecoveryResult()
                ]

        class ActivationReconciler:
            def reconcile(
                self,
                *,
                account_number,
            ):
                events.append(
                    "activate"
                )
                raise AssertionError(
                    "activation must not run "
                    "after unresolved recovery"
                )

        class PreflightReader:
            def read(
                self,
                *,
                account_number,
                evaluated_at,
            ):
                events.append(
                    "preflight"
                )

                return EquityEntryPreflightSnapshot(
                    has_existing_position=False,
                    has_open_equity_order=False,
                    has_open_option_order=False,
                    has_opening_order_today=False,
                    buying_power=Decimal("90"),
                    cash=Decimal("90"),
                )

        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                events.append(
                    "load_positions"
                )
                raise AssertionError(
                    "portfolio must not load "
                    "after unresolved recovery"
                )

        with self.assertRaisesRegex(
            RuntimeError,
            "unresolved entry placement recovery",
        ):
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                Store(),
                account_number="agentic-account",
                allowed_symbols=("AAPL",),
                universe_policy=_UNIVERSE_POLICY,
                evaluated_at=_LIVE_EVALUATED_AT,
                execution_mode=(
                    EquityEntryExecutionMode.LIVE
                ),
                placer=RecordingPlacer(),
                entry_recovery_service=(
                    RecoveryService()
                ),
                activation_reconciler=(
                    ActivationReconciler()
                ),
                preflight_reader=(
                    CleanPreflightReader()
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )

        self.assertEqual(
            events,
            [
                "recover",
            ],
        )

    def test_live_mode_blocks_when_acknowledged_entry_is_not_filled(
        self,
    ) -> None:
        events = []

        class RecoveryService:
            def recover(
                self,
                *,
                account_number,
            ):
                events.append(
                    "recover"
                )
                return []

        class ActivationReconciler:
            def reconcile(
                self,
                *,
                account_number,
            ):
                events.append(
                    "activate"
                )

                raise RuntimeError(
                    "entry activation reconciliation "
                    "left acknowledged orders unresolved"
                )

        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                events.append(
                    "load_positions"
                )
                raise AssertionError(
                    "portfolio must not load "
                    "while entry order is pending"
                )

        with self.assertRaisesRegex(
            RuntimeError,
            "acknowledged orders unresolved",
        ):
            run_robinhood_equity_strategy_cycle_from_store(
                FakeInvoker(),
                Store(),
                account_number=(
                    "agentic-account"
                ),
                allowed_symbols=(
                    "AAPL",
                ),
                universe_policy=(
                    _UNIVERSE_POLICY
                ),
                evaluated_at=(
                    _LIVE_EVALUATED_AT
                ),
                execution_mode=(
                    EquityEntryExecutionMode.LIVE
                ),
                placer=RecordingPlacer(),
                entry_recovery_service=(
                    RecoveryService()
                ),
                activation_reconciler=(
                    ActivationReconciler()
                ),
                preflight_reader=(
                    CleanPreflightReader()
                ),
                preflight_opening_debit=(
                    Decimal("10")
                ),
            )

        self.assertEqual(
            events,
            [
                "recover",
                "activate",
            ],
        )

    def test_live_preflight_blocker_stops_before_strategy(
        self,
    ) -> None:
        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                raise AssertionError(
                    "position store must not "
                    "be read after preflight "
                    "blocks entry"
                )

        invoker = FakeInvoker()

        with self.assertRaises(
            EquityEntryPreflightBlockedError
        ) as captured:
            (
                run_robinhood_equity_strategy_cycle_from_store(
                    invoker,
                    Store(),
                    account_number=(
                        "agentic-account"
                    ),
                    allowed_symbols=(
                        "AAPL",
                    ),
                    universe_policy=(
                        _UNIVERSE_POLICY
                    ),
                    evaluated_at=(
                        _LIVE_EVALUATED_AT
                    ),
                    execution_mode=(
                        EquityEntryExecutionMode
                        .LIVE
                    ),
                    placer=(
                        RecordingPlacer()
                    ),
                    activation_reconciler=(
                        RecordingActivationReconciler()
                    ),
                    entry_recovery_service=(
                        NoopEntryRecoveryService()
                    ),
                    preflight_reader=(
                        ExistingPositionPreflightReader()
                    ),
                    preflight_opening_debit=(
                        Decimal("10")
                    ),
                )
            )

        self.assertIn(
            EquityEntryPreflightBlocker
            .EXISTING_POSITION,
            captured.exception.result.blockers,
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_live_preflight_read_failure_fails_closed(
        self,
    ) -> None:
        class FailingPreflightReader:
            def read(
                self,
                *,
                account_number,
                evaluated_at,
            ):
                raise RuntimeError(
                    "portfolio unavailable"
                )

        class Store:
            def list_by_status(
                self,
                *,
                account_number,
                statuses,
            ):
                raise AssertionError(
                    "store must not be read"
                )

        with self.assertRaises(
            EquityEntryPreflightBlockedError
        ) as captured:
            (
                run_robinhood_equity_strategy_cycle_from_store(
                    FakeInvoker(),
                    Store(),
                    account_number=(
                        "agentic-account"
                    ),
                    allowed_symbols=(
                        "AAPL",
                    ),
                    universe_policy=(
                        _UNIVERSE_POLICY
                    ),
                    evaluated_at=(
                        _EVALUATED_AT
                    ),
                    execution_mode=(
                        EquityEntryExecutionMode
                        .LIVE
                    ),
                    placer=(
                        RecordingPlacer()
                    ),
                    activation_reconciler=(
                        RecordingActivationReconciler()
                    ),
                    entry_recovery_service=(
                        NoopEntryRecoveryService()
                    ),
                    preflight_reader=(
                        FailingPreflightReader()
                    ),
                    preflight_opening_debit=(
                        Decimal("10")
                    ),
                )
            )

        self.assertEqual(
            captured.exception.result.blockers,
            (
                EquityEntryPreflightBlocker
                .DATA_UNAVAILABLE,
            ),
        )


if __name__ == "__main__":
    unittest.main()