import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.domain import AssetType
from stock_agent.domain.enums import (
    OrderStatus,
)
from stock_agent.orchestration.position_close_confirmation import (
    PositionCloseConfirmation,
    PositionCloseConfirmationError,
    apply_position_close_confirmation,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


_NOW = datetime(
    2026,
    9,
    18,
    20,
    0,
    tzinfo=timezone.utc,
)


def make_state(
    *,
    status: PositionStateStatus = (
        PositionStateStatus.CLOSING
    ),
    remaining_quantity: Decimal = (
        Decimal("1")
    ),
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id="position-1",
        account_number="agentic-account",
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        opening_order_id="opening-order-1",
        entry_price=Decimal("100"),
        remaining_quantity=remaining_quantity,
        opened_at=_NOW,
        highest_executable_bid=Decimal("105"),
        trailing_armed=True,
        trailing_armed_at=_NOW,
        activation_gain_ratio=Decimal("0.04"),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
        status=status,
    )


def make_execution(
    *,
    status: OrderStatus = OrderStatus.FILLED,
    quantity: Decimal = Decimal("1"),
    filled_quantity: Decimal = Decimal("1"),
) -> RobinhoodOrderExecutionSnapshot:
    return RobinhoodOrderExecutionSnapshot(
        broker_order_id="broker-order-1",
        ref_id=(
            "00000000-0000-4000-8000-000000000001"
        ),
        status=status,
        quantity=quantity,
        filled_quantity=filled_quantity,
    )


def make_confirmation(
    *,
    position_id: str = "position-1",
    execution: (
        RobinhoodOrderExecutionSnapshot | None
    ) = None,
    confirmed_at: datetime | None = None,
) -> PositionCloseConfirmation:
    return PositionCloseConfirmation(
        position_id=position_id,
        execution=(
            execution
            if execution is not None
            else make_execution()
        ),
        confirmed_at=(
            confirmed_at
            if confirmed_at is not None
            else _NOW + timedelta(minutes=1)
        ),
    )


class PositionCloseConfirmationTests(
    unittest.TestCase
):
    def test_full_fill_closes_closing_position(
        self,
    ) -> None:
        state = make_state()

        confirmation = make_confirmation()

        updated = (
            apply_position_close_confirmation(
                state,
                confirmation,
            )
        )

        self.assertEqual(
            updated.status,
            PositionStateStatus.CLOSED,
        )

        self.assertEqual(
            updated.remaining_quantity,
            Decimal("0"),
        )

        self.assertEqual(
            updated.last_reconciled_at,
            confirmation.confirmed_at,
        )

        self.assertEqual(
            updated.version,
            state.version + 1,
        )

        self.assertEqual(
            state.status,
            PositionStateStatus.CLOSING,
        )

    def test_full_fill_closes_after_partial_quantity_sync(
        self,
    ) -> None:
        state = make_state(
            remaining_quantity=Decimal("0.4"),
        )

        confirmation = make_confirmation(
            execution=make_execution(
                quantity=Decimal("1"),
                filled_quantity=Decimal("1"),
            )
        )

        updated = (
            apply_position_close_confirmation(
                state,
                confirmation,
            )
        )

        self.assertEqual(
            updated.status,
            PositionStateStatus.CLOSED,
        )

        self.assertEqual(
            updated.remaining_quantity,
            Decimal("0"),
        )

    def test_active_position_cannot_close_directly(
        self,
    ) -> None:
        state = make_state(
            status=PositionStateStatus.ACTIVE,
        )

        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "only a closing position",
        ):
            apply_position_close_confirmation(
                state,
                make_confirmation(),
            )

    def test_reconciliation_required_position_cannot_close_directly(
        self,
    ) -> None:
        state = make_state(
            status=(
                PositionStateStatus
                .RECONCILIATION_REQUIRED
            ),
        )

        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "only a closing position",
        ):
            apply_position_close_confirmation(
                state,
                make_confirmation(),
            )

    def test_non_full_fill_cannot_close_position(
        self,
    ) -> None:
        execution = make_execution(
            status=OrderStatus.PARTIALLY_FILLED,
            quantity=Decimal("1"),
            filled_quantity=Decimal("0.4"),
        )

        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "fully filled execution",
        ):
            apply_position_close_confirmation(
                make_state(),
                make_confirmation(
                    execution=execution
                ),
            )

    def test_wrong_position_id_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "position_id does not match",
        ):
            apply_position_close_confirmation(
                make_state(),
                make_confirmation(
                    position_id="position-2"
                ),
            )

    def test_closed_position_is_idempotent(
        self,
    ) -> None:
        state = make_state(
            status=PositionStateStatus.CLOSED,
            remaining_quantity=Decimal("0"),
        )

        updated = (
            apply_position_close_confirmation(
                state,
                make_confirmation(),
            )
        )

        self.assertIs(
            updated,
            state,
        )

        self.assertEqual(
            updated.version,
            state.version,
        )

    def test_stale_confirmation_is_rejected(
        self,
    ) -> None:
        confirmation = make_confirmation(
            confirmed_at=(
                _NOW - timedelta(seconds=1)
            )
        )

        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "cannot precede",
        ):
            apply_position_close_confirmation(
                make_state(),
                confirmation,
            )


if __name__ == "__main__":
    unittest.main()