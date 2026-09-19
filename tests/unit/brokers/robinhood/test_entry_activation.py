import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.entry_activation import (
    ConfirmedEquityEntryFill,
    EntryPositionActivationError,
    activate_filled_equity_entry,
    build_active_equity_position,
)
from stock_agent.domain import (
    AssetType,
    QuoteSnapshot,
)
from stock_agent.state import (
    PositionStateStatus,
)


_FILLED_AT = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)

_QUOTE_AT = (
    _FILLED_AT
    + timedelta(
        seconds=1
    )
)


def make_fill(
) -> ConfirmedEquityEntryFill:
    return ConfirmedEquityEntryFill(
        account_number="agentic-account",
        symbol="AAPL",
        broker_order_id="broker-order-1",
        ref_id=(
            "123e4567-e89b-12d3-a456-426614174000"
        ),
        filled_quantity=Decimal(
            "0.040123"
        ),
        average_fill_price=Decimal(
            "199.40"
        ),
        filled_at=_FILLED_AT,
    )


def make_quote(
    *,
    observed_at: datetime = _QUOTE_AT,
) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol="AAPL",
        bid=Decimal("199.35"),
        observed_at=observed_at,
    )


class FakePositionStore:
    def __init__(
        self,
    ) -> None:
        self.states = {}
        self.insert_call_count = 0

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
        self.insert_call_count += 1

        if state.position_id in self.states:
            raise RuntimeError(
                "position already exists"
            )

        self.states[
            state.position_id
        ] = state


class EntryActivationTests(
    unittest.TestCase
):
    def test_builds_active_position_from_fill(
        self,
    ) -> None:
        state = build_active_equity_position(
            make_fill(),
            initial_quote=make_quote(),
        )

        self.assertEqual(
            state.account_number,
            "agentic-account",
        )

        self.assertEqual(
            state.asset_type,
            AssetType.EQUITY,
        )

        self.assertEqual(
            state.symbol,
            "AAPL",
        )

        self.assertEqual(
            state.opening_order_id,
            "broker-order-1",
        )

        self.assertEqual(
            state.entry_price,
            Decimal("199.40"),
        )

        self.assertEqual(
            state.remaining_quantity,
            Decimal("0.040123"),
        )

        self.assertEqual(
            state.status,
            PositionStateStatus.ACTIVE,
        )

        self.assertEqual(
            state.version,
            1,
        )

    def test_initializes_trailing_state_from_post_fill_bid(
        self,
    ) -> None:
        state = build_active_equity_position(
            make_fill(),
            initial_quote=make_quote(),
        )

        self.assertEqual(
            state.highest_executable_bid,
            Decimal("199.35"),
        )

        self.assertFalse(
            state.trailing_armed
        )

        self.assertIsNone(
            state.trailing_armed_at
        )

        self.assertEqual(
            state.activation_gain_ratio,
            Decimal("0.04"),
        )

        self.assertEqual(
            state.drawdown_ratio,
            Decimal("0.02"),
        )

        self.assertFalse(
            state.historical_high_unknown
        )

    def test_rejects_quote_that_predates_fill(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            EntryPositionActivationError,
            "must not predate fill",
        ):
            build_active_equity_position(
                make_fill(),
                initial_quote=make_quote(
                    observed_at=(
                        _FILLED_AT
                        - timedelta(
                            seconds=1
                        )
                    )
                ),
            )

    def test_persists_new_active_position(
        self,
    ) -> None:
        store = FakePositionStore()

        state = activate_filled_equity_entry(
            store,
            make_fill(),
            initial_quote=make_quote(),
        )

        self.assertEqual(
            store.insert_call_count,
            1,
        )

        self.assertIs(
            store.states[
                state.position_id
            ],
            state,
        )

    def test_replay_is_idempotent(
        self,
    ) -> None:
        store = FakePositionStore()

        first = activate_filled_equity_entry(
            store,
            make_fill(),
            initial_quote=make_quote(),
        )

        second = activate_filled_equity_entry(
            store,
            make_fill(),
            initial_quote=make_quote(),
        )

        self.assertEqual(
            store.insert_call_count,
            1,
        )

        self.assertIs(
            second,
            first,
        )


if __name__ == "__main__":
    unittest.main()