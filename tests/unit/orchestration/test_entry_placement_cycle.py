import unittest
from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)

from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
    EquityEntryPlacementStatus,
    execute_approved_equity_entries,
)

from stock_agent.brokers.robinhood.entry_placer import (
    RobinhoodApprovedEquityEntryPlacer,
)
from unittest.mock import patch
from types import SimpleNamespace


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


@dataclass(frozen=True)
class FakeReviewItem:
    symbol: str
    eligible_to_place: bool


@dataclass(frozen=True)
class FakePlacement:
    ref_id: str
    broker_order_id: str
    submitted_at: datetime


class FakePlacer:
    def __init__(
        self,
        *,
        failing_symbols=None,
    ) -> None:
        self.failing_symbols = set(
            failing_symbols
            or ()
        )

        self.calls = []

    def place(
        self,
        item,
        *,
        account_number,
        attempted_at,
    ):
        self.calls.append(
            (
                item.symbol,
                account_number,
                attempted_at,
            )
        )

        if (
            item.symbol
            in self.failing_symbols
        ):
            raise RuntimeError(
                "placement failed"
            )

        return FakePlacement(
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


class EntryPlacementCycleTests(
    unittest.TestCase
):
    def test_review_only_never_calls_placer(
        self,
    ) -> None:
        placer = FakePlacer()

        result = (
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=True,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .REVIEW_ONLY
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
                placer=placer,
            )
        )

        self.assertEqual(
            placer.calls,
            [],
        )

        self.assertEqual(
            len(result.items),
            1,
        )

        self.assertEqual(
            result.items[
                0
            ].status,
            EquityEntryPlacementStatus
            .REVIEW_ONLY,
        )

        self.assertEqual(
            result.placed_count,
            0,
        )

    def test_live_places_eligible_entry(
        self,
    ) -> None:
        placer = FakePlacer()

        result = (
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=True,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
                placer=placer,
            )
        )

        self.assertEqual(
            placer.calls,
            [
                (
                    "AAPL",
                    "agentic-account",
                    _NOW,
                )
            ],
        )

        self.assertEqual(
            result.placed_count,
            1,
        )

        self.assertEqual(
            result.items[
                0
            ].placement
            .broker_order_id,
            "order-AAPL",
        )

    def test_noneligible_items_never_reach_placer(
        self,
    ) -> None:
        placer = FakePlacer()

        result = (
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=False,
                    ),
                    FakeReviewItem(
                        symbol="MSFT",
                        eligible_to_place=True,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
                placer=placer,
            )
        )

        self.assertEqual(
            [
                call[0]
                for call
                in placer.calls
            ],
            [
                "MSFT",
            ],
        )

        self.assertEqual(
            [
                item.symbol
                for item
                in result.items
            ],
            [
                "MSFT",
            ],
        )

    def test_placement_failure_blocks_remaining_entries(
        self,
    ) -> None:
        placer = FakePlacer(
            failing_symbols={
                "AAPL"
            }
        )

        result = (
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=True,
                    ),
                    FakeReviewItem(
                        symbol="MSFT",
                        eligible_to_place=True,
                    ),
                    FakeReviewItem(
                        symbol="NVDA",
                        eligible_to_place=True,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
                placer=placer,
            )
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
            result.failed_count,
            1,
        )

        self.assertEqual(
            result.placed_count,
            0,
        )

        self.assertEqual(
            result.blocked_count,
            2,
        )

        self.assertEqual(
            result.failed_items[
                0
            ].symbol,
            "AAPL",
        )

        self.assertEqual(
            [
                item.symbol
                for item
                in result.blocked_items
            ],
            [
                "MSFT",
                "NVDA",
            ],
        )

        self.assertEqual(
            result.blocked_items[
                0
            ].blocked_by_symbol,
            "AAPL",
        )

        self.assertEqual(
            result.blocked_items[
                1
            ].blocked_by_symbol,
            "AAPL",
        )

    def test_live_requires_placer_before_any_execution(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "requires placer",
        ):
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=True,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
            )

    def test_no_eligible_entries_does_not_require_placer(
        self,
    ) -> None:
        result = (
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=False,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
            )
        )

        self.assertEqual(
            result.items,
            (),
        )

        self.assertEqual(
            result.placed_count,
            0,
        )

    @patch(
        "stock_agent.brokers.robinhood."
        "entry_placer."
        "place_robinhood_equity_entry"
    )
    def test_live_cycle_can_use_robinhood_placer(
        self,
        place_mock,
    ) -> None:
        from stock_agent.brokers.robinhood.entry_placement import (
            RobinhoodEquityEntryPlacementResult,
        )

        placement = (
            RobinhoodEquityEntryPlacementResult(
                ref_id="ref-AAPL",
                broker_order_id=(
                    "broker-AAPL"
                ),
                submitted_at=_NOW,
            )
        )

        place_mock.return_value = (
            placement
        )

        review = SimpleNamespace(
            plan=SimpleNamespace(
                symbol="AAPL"
            )
        )

        item = SimpleNamespace(
            symbol="AAPL",
            eligible_to_place=True,
            outcome=SimpleNamespace(
                review=review
            ),
        )

        placer = (
            RobinhoodApprovedEquityEntryPlacer(
                object(),
                object(),
            )
        )

        result = (
            execute_approved_equity_entries(
                (
                    item,
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
                placer=placer,
            )
        )

        self.assertEqual(
            result.placed_count,
            1,
        )

        self.assertEqual(
            result.placed_items[
                0
            ].placement,
            placement,
        )

    def test_successful_placement_blocks_remaining_entries(
        self,
    ) -> None:
        placer = FakePlacer(
            failing_symbols={
                "MSFT"
            }
        )

        result = (
            execute_approved_equity_entries(
                (
                    FakeReviewItem(
                        symbol="AAPL",
                        eligible_to_place=True,
                    ),
                    FakeReviewItem(
                        symbol="MSFT",
                        eligible_to_place=True,
                    ),
                    FakeReviewItem(
                        symbol="NVDA",
                        eligible_to_place=True,
                    ),
                ),
                mode=(
                    EquityEntryExecutionMode
                    .LIVE
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
                placer=placer,
            )
        )

        self.assertEqual(
            [
                call[0]
                for call in placer.calls
            ],
            [
                "AAPL",
            ],
        )

        self.assertEqual(
            result.placed_count,
            1,
        )

        self.assertEqual(
            result.failed_count,
            0,
        )

        self.assertEqual(
            result.blocked_count,
            2,
        )

        self.assertEqual(
            [
                item.symbol
                for item
                in result.blocked_items
            ],
            [
                "MSFT",
                "NVDA",
            ],
        )

        self.assertTrue(
            all(
                item.blocked_by_symbol
                == "AAPL"
                for item
                in result.blocked_items
            )
        )

if __name__ == "__main__":
    unittest.main()