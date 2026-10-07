import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from stock_agent.brokers.robinhood.entry_placement import (
    EntryPlacementStatus,
    RobinhoodEquityEntryPlacementUncertainError,
    SQLiteEquityEntryPlacementJournal,
    place_robinhood_equity_entry,
)
from stock_agent.brokers.robinhood.entry_execution_limits import (
    EquityEntryOrderLimitExceededError,
)
from stock_agent.brokers.robinhood.entry_review import (
    RobinhoodEquityEntryReview,
)
from stock_agent.strategy.entry_execution import (
    EquityEntryExecutionMode,
    EquityEntryExecutionPlan,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)

_REF_ID = (
    "123e4567-e89b-12d3-a456-426614174000"
)


class FakeInvoker:
    def __init__(
        self,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
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

        if self.error is not None:
            raise self.error

        return self.result


def fractional_review(
    *,
    approved: bool = True,
) -> RobinhoodEquityEntryReview:
    plan = EquityEntryExecutionPlan(
        symbol="AAPL",
        mode=(
            EquityEntryExecutionMode
            .FRACTIONAL_MARKET
        ),
        budget=Decimal("5"),
        dollar_amount=Decimal("5"),
        quote_observed_at=_NOW,
    )

    timestamp = (
        _NOW
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )

    return RobinhoodEquityEntryReview(
        plan=plan,
        approved=approved,
        order_checks=(
            {}
            if approved
            else {
                "test_alert": {
                    "detail": "not allowed"
                }
            }
        ),
        quote_data={
            "bid_price": "199.90",
            "ask_price": "200.10",
            "venue_bid_time": timestamp,
            "venue_ask_time": timestamp,
        },
        market_data_disclosure=None,
    )


class EntryPlacementTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.journal = (
            SQLiteEquityEntryPlacementJournal(
                Path(self.temp.name)
                / "placement.sqlite3"
            )
        )

        self.journal.initialize()

    def tearDown(
        self,
    ) -> None:
        self.temp.cleanup()

    def test_places_fractional_market_entry(
        self,
    ) -> None:
        invoker = FakeInvoker(
            result={
                "data": {
                    "order": {
                        "id": "broker-order-1",
                        "ref_id": _REF_ID,
                    }
                }
            }
        )

        result = place_robinhood_equity_entry(
            invoker,
            self.journal,
            account_number="agentic-account",
            review=fractional_review(),
            clock=lambda: _NOW,
            ref_id_factory=lambda: _REF_ID,
        )

        self.assertEqual(
            result.broker_order_id,
            "broker-order-1",
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "place_equity_order",
                    {
                        "account_number": (
                            "agentic-account"
                        ),
                        "symbol": "AAPL",
                        "side": "buy",
                        "time_in_force": "gfd",
                        "market_hours": (
                            "regular_hours"
                        ),
                        "type": "market",
                        "dollar_amount": "5",
                        "ref_id": _REF_ID,
                    },
                )
            ],
        )

        record = self.journal.get(
            _REF_ID
        )

        self.assertIsNotNone(
            record
        )

        self.assertEqual(
            record.status,
            EntryPlacementStatus
            .ACKNOWLEDGED,
        )

        self.assertEqual(
            record.broker_order_id,
            "broker-order-1",
        )

    def test_transport_failure_becomes_uncertain(
        self,
    ) -> None:
        invoker = FakeInvoker(
            error=RuntimeError(
                "transport timeout"
            )
        )

        with self.assertRaises(
            RobinhoodEquityEntryPlacementUncertainError
        ):
            place_robinhood_equity_entry(
                invoker,
                self.journal,
                account_number="agentic-account",
                review=fractional_review(),
                clock=lambda: _NOW,
                ref_id_factory=lambda: _REF_ID,
            )

        record = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            record.status,
            EntryPlacementStatus
            .UNCERTAIN,
        )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

    def test_wrong_receipt_ref_id_becomes_uncertain(
        self,
    ) -> None:
        invoker = FakeInvoker(
            result={
                "data": {
                    "order": {
                        "id": "broker-order-1",
                        "ref_id": (
                            "wrong-ref-id"
                        ),
                    }
                }
            }
        )

        with self.assertRaises(
            RobinhoodEquityEntryPlacementUncertainError
        ):
            place_robinhood_equity_entry(
                invoker,
                self.journal,
                account_number="agentic-account",
                review=fractional_review(),
                clock=lambda: _NOW,
                ref_id_factory=lambda: _REF_ID,
            )

        record = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            record.status,
            EntryPlacementStatus
            .UNCERTAIN,
        )

    def test_rejected_review_never_reaches_place(
        self,
    ) -> None:
        invoker = FakeInvoker()

        with self.assertRaisesRegex(
            ValueError,
            "review was not approved",
        ):
            place_robinhood_equity_entry(
                invoker,
                self.journal,
                account_number="agentic-account",
                review=fractional_review(
                    approved=False
                ),
                clock=lambda: _NOW,
                ref_id_factory=lambda: _REF_ID,
            )

        self.assertEqual(
            invoker.calls,
            [],
        )

        self.assertIsNone(
            self.journal.get(
                _REF_ID
            )
        )

    def test_recovers_uncertain_entry_as_acknowledged(
        self,
    ) -> None:
        invoker = FakeInvoker(
            error=RuntimeError(
                "transport timeout"
            )
        )

        with self.assertRaises(
            RobinhoodEquityEntryPlacementUncertainError
        ):
            place_robinhood_equity_entry(
                invoker,
                self.journal,
                account_number=(
                    "agentic-account"
                ),
                review=fractional_review(),
                clock=lambda: _NOW,
                ref_id_factory=lambda: _REF_ID,
            )

        recovered_at = _NOW

        self.journal.recover_acknowledged(
            _REF_ID,
            broker_order_id=(
                "broker-order-1"
            ),
            recovered_at=recovered_at,
        )

        record = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            record.status,
            EntryPlacementStatus
            .ACKNOWLEDGED,
        )

        self.assertEqual(
            record.broker_order_id,
            "broker-order-1",
        )

        self.assertEqual(
            record.acknowledged_at,
            recovered_at,
        )

        self.assertEqual(
            record.recovered_at,
            recovered_at,
        )

    def test_lists_uncertain_entries_for_account(
        self,
    ) -> None:
        other_ref_id = (
            "123e4567-e89b-12d3-a456-426614174001"
        )

        first_invoker = FakeInvoker(
            error=RuntimeError(
                "transport timeout"
            )
        )

        with self.assertRaises(
            RobinhoodEquityEntryPlacementUncertainError
        ):
            place_robinhood_equity_entry(
                first_invoker,
                self.journal,
                account_number=(
                    "agentic-account"
                ),
                review=fractional_review(),
                clock=lambda: _NOW,
                ref_id_factory=lambda: _REF_ID,
            )

        second_invoker = FakeInvoker(
            error=RuntimeError(
                "transport timeout"
            )
        )

        with self.assertRaises(
            RobinhoodEquityEntryPlacementUncertainError
        ):
            place_robinhood_equity_entry(
                second_invoker,
                self.journal,
                account_number=(
                    "other-account"
                ),
                review=fractional_review(),
                clock=lambda: _NOW,
                ref_id_factory=lambda: (
                    other_ref_id
                ),
            )

        records = (
            self.journal.list_uncertain(
                account_number=(
                    "agentic-account"
                )
            )
        )

        self.assertEqual(
            len(records),
            1,
        )

        self.assertEqual(
            records[0].ref_id,
            _REF_ID,
        )

        self.assertEqual(
            records[0].account_number,
            "agentic-account",
        )

        self.assertEqual(
            records[0].status,
            EntryPlacementStatus
            .UNCERTAIN,
        )

        self.assertIsNone(
            records[0].broker_order_id
        )

        self.assertIsNone(
            records[0].acknowledged_at
        )

        self.assertIsNone(
            records[0].recovered_at
        )

    def test_recovery_rejects_non_uncertain_entry(
        self,
    ) -> None:
        invoker = FakeInvoker(
            result={
                "data": {
                    "order": {
                        "id": (
                            "broker-order-1"
                        ),
                        "ref_id": _REF_ID,
                    }
                }
            }
        )

        place_robinhood_equity_entry(
            invoker,
            self.journal,
            account_number=(
                "agentic-account"
            ),
            review=fractional_review(),
            clock=lambda: _NOW,
            ref_id_factory=lambda: _REF_ID,
        )

        before = self.journal.get(
            _REF_ID
        )

        self.assertIsNotNone(
            before
        )

        self.assertEqual(
            before.status,
            EntryPlacementStatus
            .ACKNOWLEDGED,
        )

        self.assertEqual(
            before.broker_order_id,
            "broker-order-1",
        )

        self.assertIsNone(
            before.recovered_at
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "recovery failed",
        ):
            self.journal.recover_acknowledged(
                _REF_ID,
                broker_order_id=(
                    "other-broker-order"
                ),
                recovered_at=_NOW,
            )

        after = self.journal.get(
            _REF_ID
        )

        self.assertIsNotNone(
            after
        )

        self.assertEqual(
            after.status,
            EntryPlacementStatus
            .ACKNOWLEDGED,
        )

        self.assertEqual(
            after.broker_order_id,
            "broker-order-1",
        )

        self.assertEqual(
            after.acknowledged_at,
            before.acknowledged_at,
        )

        self.assertIsNone(
            after.recovered_at
        )

    def test_order_above_live_notional_limit_fails_before_placement(
        self,
    ) -> None:
        now = datetime(
            2026,
            10,
            5,
            18,
            0,
            tzinfo=timezone.utc,
        )

        invoker = Mock()
        journal = Mock()
        ref_id_factory = Mock(
            return_value="entry-ref-1"
        )

        plan = EquityEntryExecutionPlan(
            symbol="AAPL",
            mode=(
                EquityEntryExecutionMode
                .FRACTIONAL_MARKET
            ),
            budget=Decimal("5.01"),
            dollar_amount=Decimal("5.01"),
            quote_observed_at=now,
        )

        review = RobinhoodEquityEntryReview(
            plan=plan,
            approved=True,
            order_checks={},
            quote_data={
                "bid_price": "100",
                "ask_price": "100.10",
                "venue_bid_time": (
                    now.isoformat()
                ),
                "venue_ask_time": (
                    now.isoformat()
                ),
            },
            market_data_disclosure=None,
        )

        with self.assertRaises(
            EquityEntryOrderLimitExceededError
        ):
            place_robinhood_equity_entry(
                invoker,
                journal,
                account_number=(
                    "agentic-account"
                ),
                review=review,
                clock=lambda: now,
                ref_id_factory=(
                    ref_id_factory
                ),
            )

        invoker.call_tool.assert_not_called()

        journal.insert.assert_not_called()

        journal.transition.assert_not_called()

        journal.acknowledge.assert_not_called()

        ref_id_factory.assert_not_called()

if __name__ == "__main__":
    unittest.main()