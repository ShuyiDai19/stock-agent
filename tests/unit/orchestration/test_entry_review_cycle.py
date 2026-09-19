import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from stock_agent.domain import AssetType
from stock_agent.orchestration.entry_review_cycle import (
    EntryReviewCycleStatus,
    run_equity_entry_review_cycle,
)
from stock_agent.risk.entry_portfolio import (
    EntryRiskRequest,
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.entry_confirmation import (
    BullishEntrySnapshot,
)
from stock_agent.strategy.entry_execution import (
    EquityEntryExecutionMode,
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


class FakeInvoker:
    def __init__(
        self,
        result: Any,
    ) -> None:
        self.result = result
        self.calls = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        return self.result


def market(
    *,
    price: str = "200",
    session_open: str = "198",
    vwap: str = "199",
) -> BullishEntrySnapshot:
    return BullishEntrySnapshot(
        symbol="AAPL",
        price=Decimal(price),
        session_open=Decimal(
            session_open
        ),
        vwap=Decimal(vwap),
        recent_5m_closes=(
            Decimal("198"),
            Decimal("199"),
            Decimal("200"),
        ),
        observed_at=_NOW,
    )


def request(
) -> EntryRiskRequest:
    return EntryRiskRequest(
        symbol="AAPL",
        asset_type=AssetType.EQUITY,
        opening_cost=Decimal("8"),
    )


def execution_quote(
    *,
    bid: str = "199.90",
    ask: str = "200.10",
) -> EquityExecutionQuote:
    return EquityExecutionQuote(
        symbol="AAPL",
        bid=Decimal(bid),
        ask=Decimal(ask),
        observed_at=_NOW,
    )


def approved_review_result(
    *,
    checks=None,
    bid: str = "199.90",
    ask: str = "200.10",
):
    return {
        "data": {
            "symbol": "AAPL",
            "side": "buy",
            "type": "market",
            "dollar_amount": "8",
            "order_checks": (
                {}
                if checks is None
                else checks
            ),
            "quote_data": {
                "bid_price": bid,
                "ask_price": ask,
                "venue_bid_time": (
                    "2026-09-18T18:00:00Z"
                ),
                "venue_ask_time": (
                    "2026-09-18T18:00:00Z"
                ),
            },
        }
    }


class EntryReviewCycleTests(
    unittest.TestCase
):
    def test_approved_candidate_reaches_review(
        self,
    ) -> None:
        invoker = FakeInvoker(
            approved_review_result()
        )

        outcome = (
            run_equity_entry_review_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                market=market(),
                request=request(),
                open_positions=(),
                execution_quote=(
                    execution_quote()
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            outcome.status,
            EntryReviewCycleStatus
            .REVIEW_APPROVED,
        )

        self.assertTrue(
            outcome.eligible_to_place
        )

        self.assertIsNotNone(
            outcome.execution_plan
        )

        self.assertEqual(
            outcome.execution_plan.mode,
            EquityEntryExecutionMode
            .FRACTIONAL_MARKET,
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

        self.assertEqual(
            invoker.calls[0][0],
            "review_equity_order",
        )

    def test_failed_signal_never_calls_broker(
        self,
    ) -> None:
        invoker = FakeInvoker(
            approved_review_result()
        )

        outcome = (
            run_equity_entry_review_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                market=market(
                    price="198",
                ),
                request=request(),
                open_positions=(),
                execution_quote=(
                    execution_quote()
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            outcome.status,
            EntryReviewCycleStatus.NO_TRADE,
        )

        self.assertFalse(
            outcome.eligible_to_place
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_duplicate_underlying_never_calls_broker(
        self,
    ) -> None:
        invoker = FakeInvoker(
            approved_review_result()
        )

        existing = (
            OpenPositionRiskSnapshot(
                symbol="AAPL",
                asset_type=(
                    AssetType.EQUITY
                ),
                opening_cost=Decimal("8"),
            )
        )

        outcome = (
            run_equity_entry_review_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                market=market(),
                request=request(),
                open_positions=(
                    existing,
                ),
                execution_quote=(
                    execution_quote()
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            outcome.status,
            EntryReviewCycleStatus.NO_TRADE,
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_wide_execution_spread_skips_review(
        self,
    ) -> None:
        invoker = FakeInvoker(
            approved_review_result()
        )

        outcome = (
            run_equity_entry_review_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                market=market(),
                request=request(),
                open_positions=(),
                execution_quote=(
                    execution_quote(
                        bid="199",
                        ask="200",
                    )
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            outcome.status,
            EntryReviewCycleStatus.NO_TRADE,
        )

        self.assertIn(
            "spread",
            outcome.reason,
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_broker_order_checks_reject_review(
        self,
    ) -> None:
        invoker = FakeInvoker(
            approved_review_result(
                checks={
                    "buying_power": {
                        "detail": (
                            "insufficient "
                            "buying power"
                        )
                    }
                }
            )
        )

        outcome = (
            run_equity_entry_review_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                market=market(),
                request=request(),
                open_positions=(),
                execution_quote=(
                    execution_quote()
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            outcome.status,
            EntryReviewCycleStatus
            .REVIEW_REJECTED,
        )

        self.assertFalse(
            outcome.eligible_to_place
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

    def test_bad_review_quote_turns_into_no_trade(
        self,
    ) -> None:
        invoker = FakeInvoker(
            approved_review_result(
                bid="199",
                ask="200",
            )
        )

        outcome = (
            run_equity_entry_review_cycle(
                invoker,
                account_number=(
                    "agentic-account"
                ),
                market=market(),
                request=request(),
                open_positions=(),
                execution_quote=(
                    execution_quote()
                ),
                evaluated_at=_NOW,
            )
        )

        self.assertEqual(
            outcome.status,
            EntryReviewCycleStatus.NO_TRADE,
        )

        self.assertIn(
            "spread",
            outcome.reason,
        )

        self.assertFalse(
            outcome.eligible_to_place
        )


if __name__ == "__main__":
    unittest.main()