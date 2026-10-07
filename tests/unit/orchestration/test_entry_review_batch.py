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
    run_equity_entry_review_batch,
)
from stock_agent.orchestration.entry_review_cycle import (
    EntryReviewCycleStatus,
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
    budget: str = "5",
    priority_score: str = "0",
) -> EquityEntryReviewCandidate:
    return EquityEntryReviewCandidate(
        market=(
            BullishEntrySnapshot(
                symbol=symbol,
                price=Decimal(
                    "100"
                ),
                session_open=Decimal(
                    "99"
                ),
                vwap=Decimal(
                    "99.50"
                ),
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
            opening_cost=Decimal(
                budget
            ),
        ),
        execution_quote=(
            EquityExecutionQuote(
                symbol=symbol,
                bid=Decimal(
                    "99.95"
                ),
                ask=Decimal(
                    "100.05"
                ),
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
                f"simulated review failure "
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


class EntryReviewBatchTests(
    unittest.TestCase
):
    def test_two_candidates_can_be_approved(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate("AAPL"),
                    candidate("MSFT"),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            len(result.items),
            2,
        )

        self.assertEqual(
            len(
                result.eligible_items
            ),
            2,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_third_candidate_is_blocked_by_provisional_positions(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate("AAPL"),
                    candidate("MSFT"),
                    candidate("NVDA"),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            len(
                result.eligible_items
            ),
            2,
        )

        third = result.items[2]

        self.assertIsNotNone(
            third.outcome
        )

        self.assertEqual(
            third.outcome.status,
            EntryReviewCycleStatus
            .NO_TRADE,
        )

        # Third candidate should be rejected
        # by portfolio risk before broker review.
        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_existing_position_leaves_only_one_new_slot(
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
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate("AAPL"),
                    candidate("MSFT"),
                ),
                open_positions=(
                    existing,
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            len(
                result.eligible_items
            ),
            1,
        )

        self.assertEqual(
            result.eligible_items[
                0
            ].symbol,
            "AAPL",
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

    def test_duplicate_symbol_is_blocked_within_same_batch(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate("AAPL"),
                    candidate("AAPL"),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            len(
                result.eligible_items
            ),
            1,
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

        self.assertEqual(
            result.items[1]
            .outcome.status,
            EntryReviewCycleStatus
            .NO_TRADE,
        )

    def test_one_candidate_failure_does_not_abort_batch(
        self,
    ) -> None:
        invoker = FakeInvoker(
            failing_symbols={
                "AAPL"
            }
        )

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate("AAPL"),
                    candidate("MSFT"),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        first = result.items[0]
        second = result.items[1]

        self.assertIsInstance(
            first.error,
            RuntimeError,
        )

        self.assertIsNone(
            first.outcome,
        )

        self.assertIsNone(
            second.error,
        )

        self.assertTrue(
            second.eligible_to_place
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_higher_priority_candidate_is_reviewed_first(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate(
                        "MSFT",
                        priority_score="0.50",
                    ),
                    candidate(
                        "AAPL",
                        priority_score="0.90",
                    ),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            [
                item.symbol
                for item in result.items
            ],
            [
                "AAPL",
                "MSFT",
            ],
        )

        self.assertEqual(
            [
                call[1]["symbol"]
                for call in invoker.calls
            ],
            [
                "AAPL",
                "MSFT",
            ],
        )


    def test_priority_determines_who_gets_last_portfolio_slot(
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
                    "5"
                ),
            )
        )

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate(
                        "AAPL",
                        priority_score="0.40",
                    ),
                    candidate(
                        "MSFT",
                        priority_score="0.90",
                    ),
                ),
                open_positions=(
                    existing,
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            len(
                result.eligible_items
            ),
            1,
        )

        self.assertEqual(
            result.eligible_items[
                0
            ].symbol,
            "MSFT",
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

        self.assertEqual(
            invoker.calls[0][1][
                "symbol"
            ],
            "MSFT",
        )


    def test_equal_priority_uses_symbol_as_deterministic_tiebreaker(
        self,
    ) -> None:
        invoker = FakeInvoker()

        result = (
            run_equity_entry_review_batch(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                candidates=(
                    candidate(
                        "MSFT",
                        priority_score="0.80",
                    ),
                    candidate(
                        "AAPL",
                        priority_score="0.80",
                    ),
                ),
                open_positions=(),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            [
                item.symbol
                for item in result.items
            ],
            [
                "AAPL",
                "MSFT",
            ],
        )


    def test_rejects_nonfinite_priority_score(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "priority_score must be finite",
        ):
            candidate(
                "AAPL",
                priority_score="NaN",
            )


if __name__ == "__main__":
    unittest.main()