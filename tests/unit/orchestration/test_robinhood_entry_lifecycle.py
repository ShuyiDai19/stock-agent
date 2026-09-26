import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.entry_activation_reconciler import (
    RobinhoodEquityEntryActivationReconciler,
)
from stock_agent.brokers.robinhood.entry_placement import (
    EntryPlacementStatus,
    EquityEntryPlacementRecord,
    SQLiteEquityEntryPlacementJournal,
)
from stock_agent.brokers.robinhood.entry_placement_recovery import (
    EquityEntryPlacementRecoveryService,
)
from stock_agent.brokers.robinhood.mcp_order_lookup import (
    MCPRobinhoodOrderLookup,
)
from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
)
from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
)
from stock_agent.orchestration.robinhood_strategy_cycle import (
    run_robinhood_equity_strategy_cycle_from_store,
)
from stock_agent.state import (
    PositionStateStatus,
    SQLitePositionStateStore,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightSnapshot,
)


_REF_ID = (
    "123e4567-e89b-12d3-a456-426614174000"
)

_ACCOUNT_NUMBER = "agentic-account"

_SYMBOL = "AAPL"

_ATTEMPTED_AT = datetime(
    2026,
    9,
    18,
    13,
    45,
    tzinfo=timezone.utc,
)

_RECOVERED_AT = datetime(
    2026,
    9,
    18,
    13,
    47,
    tzinfo=timezone.utc,
)

_FILL_TIME = (
    "2026-09-18T13:46:30Z"
)


class LifecycleFakeInvoker:
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
            == "get_equity_orders"
        ):
            # Recovery lookup:
            #
            # UNCERTAIN
            # → search account/symbol history
            # → exact ref_id FOUND
            if "order_id" not in arguments:
                return {
                    "data": {
                        "orders": [
                            {
                                "id": (
                                    "broker-order-1"
                                ),
                                "ref_id": _REF_ID,
                                "symbol": _SYMBOL,
                            }
                        ],
                        "next": None,
                    }
                }

            # Activation lookup:
            #
            # ACKNOWLEDGED
            # → specific broker order
            # → FILLED
            self.assert_activation_lookup(
                arguments
            )

            return {
                "data": {
                    "orders": [
                        {
                            "id": (
                                "broker-order-1"
                            ),
                            "ref_id": _REF_ID,
                            "symbol": _SYMBOL,
                            "side": "buy",
                            "state": "filled",
                            "quantity": None,
                            "cumulative_quantity": (
                                "0.05"
                            ),
                            "average_price": (
                                "100"
                            ),
                            "last_transaction_at": (
                                _FILL_TIME
                            ),
                        }
                    ],
                    "next": None,
                }
            }

        if (
            tool_name
            == "get_equity_quotes"
        ):
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

        if (
            tool_name
            == "get_equity_fundamentals"
        ):
            return {
                "data": {
                    "results": [
                        {
                            "symbol": _SYMBOL,
                            "average_volume_30_days": (
                                "5000000"
                            ),
                            "market_cap": (
                                "10000000000"
                            ),
                        }
                    ],
                    "not_found": [],
                }
            }

        if (
            tool_name
            == "get_equity_historicals"
        ):
            return {
                "data": {
                    "results": [
                        {
                            "symbol": _SYMBOL,
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

        if (
            tool_name
            == "review_equity_order"
        ):
            raise AssertionError(
                "existing recovered position "
                "must prevent a duplicate entry review"
            )

        raise AssertionError(
            f"unexpected MCP tool: {tool_name}"
        )

    def assert_activation_lookup(
        self,
        arguments,
    ) -> None:
        if (
            arguments.get(
                "account_number"
            )
            != _ACCOUNT_NUMBER
        ):
            raise AssertionError(
                "activation lookup used "
                "wrong account"
            )

        if (
            arguments.get(
                "order_id"
            )
            != "broker-order-1"
        ):
            raise AssertionError(
                "activation lookup used "
                "wrong broker order"
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
            "recovered active position "
            "must prevent duplicate placement"
        )

class CleanPreflightReader:
    def read(
        self,
        *,
        account_number,
        evaluated_at,
    ):
        return EquityEntryPreflightSnapshot(
            has_existing_position=False,
            has_open_equity_order=False,
            has_open_option_order=False,
            has_opening_order_today=False,
            buying_power=Decimal("90"),
            cash=Decimal("90"),
        )


class RobinhoodEntryLifecycleTests(
    unittest.TestCase
):
    def test_uncertain_entry_recovers_activates_and_blocks_duplicate_entry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            entry_journal = (
                SQLiteEquityEntryPlacementJournal(
                    root
                    / "entry-placement.sqlite3"
                )
            )

            entry_journal.initialize()

            position_store = (
                SQLitePositionStateStore(
                    root
                    / "positions.sqlite3"
                )
            )

            position_store.initialize()

            # Simulate process restart after:
            #
            # place_equity_order()
            # → broker may have accepted
            # → transport outcome uncertain
            entry_journal.insert(
                EquityEntryPlacementRecord(
                    ref_id=_REF_ID,
                    account_number=(
                        _ACCOUNT_NUMBER
                    ),
                    symbol=_SYMBOL,
                    arguments={
                        "symbol": _SYMBOL,
                    },
                    attempted_at=(
                        _ATTEMPTED_AT
                    ),
                    status=(
                        EntryPlacementStatus
                        .UNCERTAIN
                    ),
                )
            )

            invoker = (
                LifecycleFakeInvoker()
            )

            recovery_service = (
                EquityEntryPlacementRecoveryService(
                    entry_journal,
                    MCPRobinhoodOrderLookup(
                        invoker
                    ),
                    clock=lambda: (
                        _RECOVERED_AT
                    ),
                )
            )

            activation_reconciler = (
                RobinhoodEquityEntryActivationReconciler(
                    invoker,
                    entry_journal,
                    position_store,
                    MCPRobinhoodEquityQuoteProvider(
                        invoker
                    ),
                )
            )

            result = (
                run_robinhood_equity_strategy_cycle_from_store(
                    invoker,
                    position_store,
                    account_number=(
                        _ACCOUNT_NUMBER
                    ),
                    allowed_symbols=(
                        _SYMBOL,
                    ),
                    universe_policy=(
                        EquityUniverseScreeningPolicy(
                            min_average_volume_30d=(
                                Decimal(
                                    "1000000"
                                )
                            ),
                            min_market_cap=(
                                Decimal(
                                    "1000000000"
                                )
                            ),
                        )
                    ),
                    evaluated_at=datetime(
                        2026,
                        9,
                        18,
                        14,
                        30,
                        tzinfo=timezone.utc,
                    ),
                    execution_mode=(
                        EquityEntryExecutionMode
                        .LIVE
                    ),
                    placer=(
                        ExplodingPlacer()
                    ),
                    entry_recovery_service=(
                        recovery_service
                    ),
                    activation_reconciler=(
                        activation_reconciler
                    ),
                    preflight_reader=(
                        CleanPreflightReader()
                    ),
                    preflight_opening_debit=(
                        Decimal("10")
                    ),
                )
            )

            # Recovery:
            #
            # UNCERTAIN → ACKNOWLEDGED
            #
            # Activation then moves the journal
            # to its terminal ACTIVATED state.
            placement = (
                entry_journal.get(
                    _REF_ID
                )
            )

            self.assertEqual(
                placement.status,
                EntryPlacementStatus
                .ACTIVATED,
            )

            self.assertEqual(
                placement.broker_order_id,
                "broker-order-1",
            )

            self.assertEqual(
                placement.recovered_at,
                _RECOVERED_AT,
            )

            # FILLED broker order became a real
            # locally tracked ACTIVE position.
            position_id = (
                f"{_ACCOUNT_NUMBER}:"
                f"equity:{_SYMBOL}:"
                "broker-order-1"
            )

            position = (
                position_store.get(
                    position_id
                )
            )

            self.assertIsNotNone(
                position
            )

            self.assertEqual(
                position.status,
                PositionStateStatus.ACTIVE,
            )

            self.assertEqual(
                position.symbol,
                _SYMBOL,
            )

            self.assertEqual(
                position.opening_order_id,
                "broker-order-1",
            )

            self.assertEqual(
                position.remaining_quantity,
                Decimal("0.05"),
            )

            self.assertEqual(
                position.entry_price,
                Decimal("100"),
            )

            # The newly activated position must be
            # visible to portfolio risk immediately.
            self.assertEqual(
                result.eligible_entry_count,
                0,
            )

            self.assertEqual(
                result.placement_count,
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

            order_calls = [
                call
                for call in invoker.calls
                if (
                    call[0]
                    == "get_equity_orders"
                )
            ]

            # One lookup recovers the uncertain
            # placement; the second confirms fill
            # for activation.
            self.assertEqual(
                len(order_calls),
                2,
            )

            self.assertNotIn(
                "order_id",
                order_calls[0][1],
            )

            self.assertEqual(
                order_calls[0][1][
                    "symbol"
                ],
                _SYMBOL,
            )

            self.assertEqual(
                order_calls[1][1][
                    "order_id"
                ],
                "broker-order-1",
            )


if __name__ == "__main__":
    unittest.main()