import tempfile
import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.entry_fill import (
    activate_acknowledged_equity_entries,
)
from stock_agent.brokers.robinhood.entry_placement import (
    EntryPlacementStatus,
    EquityEntryPlacementRecord,
    SQLiteEquityEntryPlacementJournal,
)
from stock_agent.domain import (
    QuoteSnapshot,
)
from stock_agent.state import (
    PositionStateStatus,
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


def make_order_result(
    *,
    state: str = "filled",
):
    return {
        "data": {
            "orders": [
                {
                    "id": "broker-order-1",
                    "ref_id": _REF_ID,
                    "symbol": "AAPL",
                    "side": "buy",
                    "type": "market",
                    "state": state,
                    "quantity": None,
                    "cumulative_quantity": (
                        "0.040123"
                    ),
                    "average_price": (
                        "199.40"
                    ),
                    "last_transaction_at": (
                        _NOW
                        .isoformat()
                        .replace(
                            "+00:00",
                            "Z",
                        )
                    ),
                }
            ]
        }
    }


class FakeInvoker:
    def __init__(
        self,
        result,
    ) -> None:
        self.result = result
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

        return self.result


class FakeQuoteProvider:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def get_quote(
        self,
        symbol,
    ):
        self.calls.append(
            symbol
        )

        return QuoteSnapshot(
            symbol=symbol,
            bid=Decimal("199.35"),
            observed_at=(
                _NOW
                + timedelta(
                    seconds=1
                )
            ),
        )


class FakePositionStore:
    def __init__(
        self,
    ) -> None:
        self.states = {}

    def get(
        self,
        position_id,
    ):
        return self.states.get(
            position_id
        )

    def insert(
        self,
        state,
    ) -> None:
        if state.position_id in self.states:
            raise RuntimeError(
                "position already exists"
            )

        self.states[
            state.position_id
        ] = state


class EntryActivationSweepTests(
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

        self.store = (
            FakePositionStore()
        )

        self.quote_provider = (
            FakeQuoteProvider()
        )

    def tearDown(
        self,
    ) -> None:
        self.temp.cleanup()

    def insert_acknowledged(
        self,
        *,
        account_number=(
            "agentic-account"
        ),
    ) -> None:
        self.journal.insert(
            EquityEntryPlacementRecord(
                ref_id=_REF_ID,
                account_number=(
                    account_number
                ),
                symbol="AAPL",
                arguments={
                    "symbol": "AAPL",
                    "side": "buy",
                },
                attempted_at=_NOW,
                status=(
                    EntryPlacementStatus
                    .ACKNOWLEDGED
                ),
                broker_order_id=(
                    "broker-order-1"
                ),
                acknowledged_at=_NOW,
            )
        )

    def test_filled_acknowledged_order_becomes_activated(
        self,
    ) -> None:
        self.insert_acknowledged()

        invoker = FakeInvoker(
            make_order_result()
        )

        positions = (
            activate_acknowledged_equity_entries(
                invoker,
                self.journal,
                self.store,
                self.quote_provider,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            len(positions),
            1,
        )

        self.assertEqual(
            positions[0].status,
            PositionStateStatus.ACTIVE,
        )

        record = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            record.status,
            EntryPlacementStatus
            .ACTIVATED,
        )

    def test_unfilled_order_remains_acknowledged(
        self,
    ) -> None:
        self.insert_acknowledged()

        invoker = FakeInvoker(
            make_order_result(
                state="confirmed"
            )
        )

        positions = (
            activate_acknowledged_equity_entries(
                invoker,
                self.journal,
                self.store,
                self.quote_provider,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            positions,
            [],
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
            self.store.states,
            {},
        )

        self.assertEqual(
            self.quote_provider.calls,
            [],
        )

    def test_activated_order_is_not_polled_again(
        self,
    ) -> None:
        self.insert_acknowledged()

        self.journal.transition(
            _REF_ID,
            expected_status=(
                EntryPlacementStatus
                .ACKNOWLEDGED
            ),
            new_status=(
                EntryPlacementStatus
                .ACTIVATED
            ),
        )

        invoker = FakeInvoker(
            make_order_result()
        )

        positions = (
            activate_acknowledged_equity_entries(
                invoker,
                self.journal,
                self.store,
                self.quote_provider,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            positions,
            [],
        )

        self.assertEqual(
            invoker.calls,
            [],
        )

    def test_does_not_process_other_account(
        self,
    ) -> None:
        self.insert_acknowledged(
            account_number="other-account"
        )

        invoker = FakeInvoker(
            make_order_result()
        )

        positions = (
            activate_acknowledged_equity_entries(
                invoker,
                self.journal,
                self.store,
                self.quote_provider,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            positions,
            [],
        )

        self.assertEqual(
            invoker.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()