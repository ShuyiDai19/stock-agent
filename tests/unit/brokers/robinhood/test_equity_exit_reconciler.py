import unittest
from dataclasses import replace
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.equity_exit_reconciler import (
    RobinhoodEquityExitReconciler,
    RobinhoodEquityExitReconciliationError,
)
from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


_NOW = datetime(
    2026,
    9,
    24,
    15,
    0,
    tzinfo=timezone.utc,
)


def make_state(
    *,
    status: PositionStateStatus,
    asset_type: AssetType = (
        AssetType.EQUITY
    ),
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id=(
            "account-0000:"
            "equity:AAPL:order-123"
        ),
        account_number=(
            "account-0000"
        ),
        asset_type=asset_type,
        symbol="AAPL",
        opening_order_id="order-123",
        entry_price=Decimal("100"),
        remaining_quantity=(
            Decimal("0.031")
        ),
        opened_at=_NOW,
        highest_executable_bid=(
            Decimal("110")
        ),
        trailing_armed=True,
        trailing_armed_at=_NOW,
        activation_gain_ratio=(
            Decimal("0.04")
        ),
        drawdown_ratio=(
            Decimal("0.02")
        ),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
        status=status,
        option_id=None,
        historical_high_unknown=False,
        version=3,
    )


class FakeStore:
    def __init__(
        self,
        states=(),
    ) -> None:
        self.states = {
            state.position_id:
                state
            for state in states
        }

        self.events = []

    def list_by_status(
        self,
        *,
        account_number,
        statuses,
    ):
        self.events.append(
            "list_closing"
        )

        return [
            state
            for state
            in self.states.values()
            if (
                state.account_number
                == account_number
                and state.status
                in statuses
            )
        ]


class RecordingStateReconciler:
    def __init__(
        self,
        store,
        *,
        repair_state=None,
    ) -> None:
        self.store = store
        self.repair_state = (
            repair_state
        )
        self.calls = []

    def reconcile(
        self,
        *,
        account_number,
    ):
        self.calls.append(
            account_number
        )
        self.store.events.append(
            "repair"
        )

        if (
            self.repair_state
            is not None
        ):
            self.store.states[
                self.repair_state
                .position_id
            ] = self.repair_state

        return ()


class FakeCloseService:
    def __init__(
        self,
        store,
        *,
        result=None,
        error=None,
    ) -> None:
        self.store = store
        self.result = result
        self.error = error
        self.calls = []

    def confirm_if_filled(
        self,
        *,
        position_id,
    ):
        self.calls.append(
            position_id
        )

        self.store.events.append(
            "confirm"
        )

        if self.error is not None:
            raise self.error

        if self.result is not None:
            self.store.states[
                position_id
            ] = self.result

        return self.result


class RobinhoodEquityExitReconcilerTests(
    unittest.TestCase
):
    def test_repairs_before_close_confirmation(
        self,
    ) -> None:
        active = make_state(
            status=(
                PositionStateStatus
                .ACTIVE
            )
        )

        closing = replace(
            active,
            status=(
                PositionStateStatus
                .CLOSING
            ),
            version=4,
        )

        closed = replace(
            closing,
            status=(
                PositionStateStatus
                .CLOSED
            ),
            remaining_quantity=(
                Decimal("0")
            ),
            version=5,
        )

        store = FakeStore(
            [active]
        )

        state_reconciler = (
            RecordingStateReconciler(
                store,
                repair_state=closing,
            )
        )

        close_service = (
            FakeCloseService(
                store,
                result=closed,
            )
        )

        reconciler = (
            RobinhoodEquityExitReconciler(
                state_reconciler,
                close_service,
                store,
            )
        )

        result = reconciler.reconcile(
            account_number=(
                "account-0000"
            )
        )

        self.assertEqual(
            result,
            (closed,),
        )

        self.assertEqual(
            store.events,
            [
                "repair",
                "list_closing",
                "confirm",
                "list_closing",
            ],
        )

    def test_pending_closing_position_blocks_cycle(
        self,
    ) -> None:
        closing = make_state(
            status=(
                PositionStateStatus
                .CLOSING
            )
        )

        store = FakeStore(
            [closing]
        )

        state_reconciler = (
            RecordingStateReconciler(
                store
            )
        )

        close_service = (
            FakeCloseService(
                store,
                result=None,
            )
        )

        reconciler = (
            RobinhoodEquityExitReconciler(
                state_reconciler,
                close_service,
                store,
            )
        )

        with self.assertRaisesRegex(
            RobinhoodEquityExitReconciliationError,
            "left closing positions unresolved",
        ):
            reconciler.reconcile(
                account_number=(
                    "account-0000"
                )
            )

        self.assertEqual(
            close_service.calls,
            [
                closing.position_id,
            ],
        )

    def test_no_closing_position_is_clean(
        self,
    ) -> None:
        active = make_state(
            status=(
                PositionStateStatus
                .ACTIVE
            )
        )

        store = FakeStore(
            [active]
        )

        state_reconciler = (
            RecordingStateReconciler(
                store
            )
        )

        close_service = (
            FakeCloseService(
                store
            )
        )

        reconciler = (
            RobinhoodEquityExitReconciler(
                state_reconciler,
                close_service,
                store,
            )
        )

        result = reconciler.reconcile(
            account_number=(
                "account-0000"
            )
        )

        self.assertEqual(
            result,
            (),
        )

        self.assertEqual(
            close_service.calls,
            [],
        )

    def test_close_confirmation_error_propagates(
        self,
    ) -> None:
        closing = make_state(
            status=(
                PositionStateStatus
                .CLOSING
            )
        )

        store = FakeStore(
            [closing]
        )

        close_service = (
            FakeCloseService(
                store,
                error=RuntimeError(
                    "broker unavailable"
                ),
            )
        )

        reconciler = (
            RobinhoodEquityExitReconciler(
                RecordingStateReconciler(
                    store
                ),
                close_service,
                store,
            )
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "broker unavailable",
        ):
            reconciler.reconcile(
                account_number=(
                    "account-0000"
                )
            )

    def test_non_closed_confirmation_fails_closed(
        self,
    ) -> None:
        closing = make_state(
            status=(
                PositionStateStatus
                .CLOSING
            )
        )

        store = FakeStore(
            [closing]
        )

        close_service = (
            FakeCloseService(
                store,
                result=closing,
            )
        )

        reconciler = (
            RobinhoodEquityExitReconciler(
                RecordingStateReconciler(
                    store
                ),
                close_service,
                store,
            )
        )

        with self.assertRaisesRegex(
            RobinhoodEquityExitReconciliationError,
            "non-closed state",
        ):
            reconciler.reconcile(
                account_number=(
                    "account-0000"
                )
            )

    def test_option_closing_state_is_not_owned_by_equity_reconciler(
        self,
    ) -> None:
        option_state = replace(
            make_state(
                status=(
                    PositionStateStatus
                    .CLOSING
                )
            ),
            position_id=(
                "account-0000:"
                "option:AAPL:order-999"
            ),
            asset_type=(
                AssetType.OPTION
            ),
            option_id=(
                "option-contract-1"
            ),
        )

        store = FakeStore(
            [option_state]
        )

        close_service = (
            FakeCloseService(
                store
            )
        )

        reconciler = (
            RobinhoodEquityExitReconciler(
                RecordingStateReconciler(
                    store
                ),
                close_service,
                store,
            )
        )

        result = reconciler.reconcile(
            account_number=(
                "account-0000"
            )
        )

        self.assertEqual(
            result,
            (),
        )

        self.assertEqual(
            close_service.calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()