import unittest
from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace
from unittest.mock import patch

from stock_agent.brokers.robinhood.entry_placer import (
    RobinhoodApprovedEquityEntryPlacer,
)
from stock_agent.brokers.robinhood.entry_placement import (
    RobinhoodEquityEntryPlacementResult,
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
    pass


class FakeJournal:
    pass


def make_item(
    *,
    symbol: str = "AAPL",
    eligible: bool = True,
    review_symbol: str = "AAPL",
    include_outcome: bool = True,
    include_review: bool = True,
):
    review = None

    if include_review:
        review = SimpleNamespace(
            plan=SimpleNamespace(
                symbol=review_symbol,
            )
        )

    outcome = None

    if include_outcome:
        outcome = SimpleNamespace(
            review=review,
        )

    return SimpleNamespace(
        symbol=symbol,
        eligible_to_place=eligible,
        outcome=outcome,
    )


class RobinhoodApprovedEquityEntryPlacerTests(
    unittest.TestCase
):
    @patch(
        "stock_agent.brokers.robinhood."
        "entry_placer."
        "place_robinhood_equity_entry"
    )
    def test_forwards_approved_review_to_entry_placement(
        self,
        place_mock,
    ) -> None:
        def clock():
            return _NOW

        expected = (
            RobinhoodEquityEntryPlacementResult(
                ref_id="ref-1",
                broker_order_id=(
                    "broker-order-1"
                ),
                submitted_at=_NOW,
            )
        )

        place_mock.return_value = (
            expected
        )

        invoker = FakeInvoker()
        journal = FakeJournal()

        placer = (
            RobinhoodApprovedEquityEntryPlacer(
                invoker,
                journal,
                clock=clock,
            )
        )

        item = make_item()

        result = placer.place(
            item,
            account_number=(
                "agentic-account"
            ),
            attempted_at=_NOW,
        )

        self.assertEqual(
            result,
            expected,
        )

        place_mock.assert_called_once()

        args = (
            place_mock.call_args.args
        )

        kwargs = (
            place_mock.call_args.kwargs
        )

        self.assertIs(
            args[0],
            invoker,
        )

        self.assertIs(
            args[1],
            journal,
        )

        self.assertEqual(
            kwargs[
                "account_number"
            ],
            "agentic-account",
        )

        self.assertIs(
            kwargs["review"],
            item.outcome.review,
        )

        self.assertIs(
            kwargs["clock"],
            clock,
        )

        self.assertNotIn(
            "ref_id_factory",
            kwargs,
        )

    @patch(
        "stock_agent.brokers.robinhood."
        "entry_placer."
        "place_robinhood_equity_entry"
    )
    def test_forwards_ref_id_factory(
        self,
        place_mock,
    ) -> None:
        place_mock.return_value = (
            RobinhoodEquityEntryPlacementResult(
                ref_id="fixed-ref",
                broker_order_id="order-1",
                submitted_at=_NOW,
            )
        )

        def clock():
            return _NOW

        def ref_id_factory():
            return "fixed-ref"

        placer = (
            RobinhoodApprovedEquityEntryPlacer(
                FakeInvoker(),
                FakeJournal(),
                clock=clock,
                ref_id_factory=(
                    ref_id_factory
                ),
            )
        )

        placer.place(
            make_item(),
            account_number=(
                "agentic-account"
            ),
            attempted_at=_NOW,
        )

        self.assertIs(
            place_mock.call_args.kwargs[
                "ref_id_factory"
            ],
            ref_id_factory,
        )

        self.assertIs(
            place_mock.call_args.kwargs[
                "clock"
            ],
            clock,
        )

    @patch(
        "stock_agent.brokers.robinhood."
        "entry_placer."
        "place_robinhood_equity_entry"
    )
    def test_noneligible_item_is_rejected_before_placement(
        self,
        place_mock,
    ) -> None:
        placer = (
            RobinhoodApprovedEquityEntryPlacer(
                FakeInvoker(),
                FakeJournal(),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "not eligible",
        ):
            placer.place(
                make_item(
                    eligible=False
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
            )

        place_mock.assert_not_called()

    @patch(
        "stock_agent.brokers.robinhood."
        "entry_placer."
        "place_robinhood_equity_entry"
    )
    def test_missing_review_is_rejected(
        self,
        place_mock,
    ) -> None:
        placer = (
            RobinhoodApprovedEquityEntryPlacer(
                FakeInvoker(),
                FakeJournal(),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "broker review",
        ):
            placer.place(
                make_item(
                    include_review=False,
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
            )

        place_mock.assert_not_called()

    @patch(
        "stock_agent.brokers.robinhood."
        "entry_placer."
        "place_robinhood_equity_entry"
    )
    def test_symbol_mismatch_is_rejected(
        self,
        place_mock,
    ) -> None:
        placer = (
            RobinhoodApprovedEquityEntryPlacer(
                FakeInvoker(),
                FakeJournal(),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "symbol",
        ):
            placer.place(
                make_item(
                    symbol="AAPL",
                    review_symbol="MSFT",
                ),
                account_number=(
                    "agentic-account"
                ),
                attempted_at=_NOW,
            )

        place_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()