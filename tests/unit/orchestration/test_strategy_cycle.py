import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.domain import (
    AssetType,
)
from stock_agent.orchestration.entry_review_batch import (
    EquityEntryReviewCandidate,
)
from stock_agent.orchestration.strategy_cycle import (
    EquityStrategyCycleInput,
    run_equity_strategy_cycle,
)
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_execution import (
    EquityExecutionQuote,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def candidate(
    symbol: str,
    *,
    priority_score: str = "0",
) -> EquityEntryReviewCandidate:
    return EquityEntryReviewCandidate(
        market=(
            BullishEntrySnapshot(
                symbol=symbol,
                price=Decimal("100"),
                session_open=Decimal("99"),
                vwap=Decimal("99.50"),
                recent_5m_closes=(
                    Decimal("99"),
                    Decimal("99.50"),
                    Decimal("100"),
                ),
                observed_at=_NOW,
            )
        ),
        request=EntryRiskRequest(
            symbol=symbol,
            asset_type=(
                AssetType.EQUITY
            ),
            opening_cost=Decimal("8"),
        ),
        execution_quote=(
            EquityExecutionQuote(
                symbol=symbol,
                bid=Decimal("99.95"),
                ask=Decimal("100.05"),
                observed_at=_NOW,
            )
        ),
        priority_score=Decimal(
            priority_score
        ),
    )


class FakeInvoker:
    def __init__(
        self,
        *,
        failing_symbols=None,
    ) -> None:
        self.failing_symbols = set(
            failing_symbols or ()
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
            "symbol"
        ]

        if symbol in self.failing_symbols:
            raise RuntimeError(
                f"simulated failure "
                f"for {symbol}"
            )

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
                        "99.95"
                    ),
                    "ask_price": (
                        "100.05"
                    ),
                    "venue_bid_time": (
                        "2026-09-18"
                        "T18:00:00Z"
                    ),
                    "venue_ask_time": (
                        "2026-09-18"
                        "T18:00:00Z"
                    ),
                },
            }
        }


class StrategyCycleTests(
    unittest.TestCase
):
    def test_cycle_exposes_eligible_entries(
        self,
    ) -> None:
        invoker = FakeInvoker()

        cycle_input = (
            EquityStrategyCycleInput(
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate(
                        "AAPL",
                        priority_score="0.9",
                    ),
                    candidate(
                        "MSFT",
                        priority_score="0.8",
                    ),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        outcome = (
            run_equity_strategy_cycle(
                invoker,
                cycle_input,
            )
        )

        self.assertEqual(
            outcome.reviewed_candidate_count,
            2,
        )

        self.assertEqual(
            outcome.eligible_entry_count,
            2,
        )

        self.assertEqual(
            outcome.error_count,
            0,
        )

        self.assertEqual(
            [
                item.symbol
                for item
                in outcome.eligible_entries
            ],
            [
                "AAPL",
                "MSFT",
            ],
        )

    def test_existing_position_limits_cycle_capacity(
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

        cycle_input = (
            EquityStrategyCycleInput(
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate(
                        "AAPL",
                        priority_score="0.9",
                    ),
                    candidate(
                        "MSFT",
                        priority_score="0.8",
                    ),
                ),
                open_positions=(
                    existing,
                ),
                evaluated_at=_NOW,
            )
        )

        outcome = (
            run_equity_strategy_cycle(
                invoker,
                cycle_input,
            )
        )

        self.assertEqual(
            outcome.eligible_entry_count,
            1,
        )

        self.assertEqual(
            outcome.eligible_entries[
                0
            ].symbol,
            "AAPL",
        )

    def test_cycle_preserves_candidate_errors(
        self,
    ) -> None:
        invoker = FakeInvoker(
            failing_symbols={
                "AAPL"
            }
        )

        cycle_input = (
            EquityStrategyCycleInput(
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate(
                        "AAPL",
                        priority_score="0.9",
                    ),
                    candidate(
                        "MSFT",
                        priority_score="0.8",
                    ),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        outcome = (
            run_equity_strategy_cycle(
                invoker,
                cycle_input,
            )
        )

        self.assertEqual(
            outcome.error_count,
            1,
        )

        self.assertEqual(
            outcome.errors[
                0
            ].symbol,
            "AAPL",
        )

        self.assertEqual(
            outcome.eligible_entry_count,
            1,
        )

        self.assertEqual(
            outcome.eligible_entries[
                0
            ].symbol,
            "MSFT",
        )

    def test_empty_candidate_set_is_valid_cycle(
        self,
    ) -> None:
        invoker = FakeInvoker()

        cycle_input = (
            EquityStrategyCycleInput(
                account_number=(
                    "agentic-account"
                ),
                candidates=(),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        outcome = (
            run_equity_strategy_cycle(
                invoker,
                cycle_input,
            )
        )

        self.assertEqual(
            outcome.reviewed_candidate_count,
            0,
        )

        self.assertEqual(
            outcome.eligible_entry_count,
            0,
        )

        self.assertEqual(
            outcome.error_count,
            0,
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_rejects_naive_cycle_time(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "timezone-aware",
        ):
            EquityStrategyCycleInput(
                account_number=(
                    "agentic-account"
                ),
                candidates=(),
                open_positions=(),
                evaluated_at=(
                    datetime(
                        2026,
                        9,
                        18,
                        18,
                        0,
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()