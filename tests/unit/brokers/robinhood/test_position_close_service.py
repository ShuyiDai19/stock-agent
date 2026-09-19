import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from stock_agent.brokers.robinhood.order_execution import (
    RobinhoodOrderExecutionSnapshot,
)
from stock_agent.brokers.robinhood.position_close_service import (
    EquityPositionCloseConfirmationService,
)
from stock_agent.domain import AssetType
from stock_agent.domain.enums import OrderStatus
from stock_agent.orchestration.position_close_confirmation import (
    PositionCloseConfirmationError,
)
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.sqlite_store import (
    SQLitePositionStateStore,
)
from stock_agent.state.store import (
    ConcurrentStateUpdateError,
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
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id="position-1",
        account_number="agentic-account",
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        opening_order_id="opening-order-1",
        entry_price=Decimal("100"),
        remaining_quantity=Decimal("1"),
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


def make_filled_execution(
) -> RobinhoodOrderExecutionSnapshot:
    return RobinhoodOrderExecutionSnapshot(
        broker_order_id="broker-order-1",
        ref_id=(
            "00000000-0000-4000-8000-000000000001"
        ),
        status=OrderStatus.FILLED,
        quantity=Decimal("1"),
        filled_quantity=Decimal("1"),
    )


class FakeExecutionReader:
    def __init__(
        self,
        execution: (
            RobinhoodOrderExecutionSnapshot | None
        ),
        *,
        before_return=None,
    ) -> None:
        self.execution = execution
        self.before_return = before_return
        self.calls = []

    def read(
        self,
        *,
        account_number: str,
        broker_order_id: str,
        ref_id: str,
    ):
        self.calls.append(
            (
                account_number,
                broker_order_id,
                ref_id,
            )
        )

        if self.before_return is not None:
            self.before_return()

        return self.execution


class EquityPositionCloseConfirmationServiceTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        self.store = SQLitePositionStateStore(
            Path(
                self.temp_directory.name
            )
            / "positions.sqlite3"
        )

        self.store.initialize()

    def tearDown(
        self,
    ) -> None:
        self.temp_directory.cleanup()

    def make_service(
        self,
        reader,
    ):
        return (
            EquityPositionCloseConfirmationService(
                self.store,
                reader,
                clock=lambda: (
                    _NOW
                    + timedelta(minutes=1)
                ),
            )
        )

    def test_full_fill_is_persisted_as_closed(
        self,
    ) -> None:
        state = make_state()
        self.store.insert(state)

        reader = FakeExecutionReader(
            make_filled_execution()
        )

        service = self.make_service(
            reader
        )

        updated = service.confirm_if_filled(
            position_id=state.position_id,
            broker_order_id="broker-order-1",
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
        )

        self.assertIsNotNone(
            updated
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
            updated.version,
            state.version + 1,
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertIsNotNone(
            persisted
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.CLOSED,
        )

        self.assertEqual(
            persisted.remaining_quantity,
            Decimal("0"),
        )

    def test_no_full_fill_evidence_does_not_modify_state(
        self,
    ) -> None:
        state = make_state()
        self.store.insert(state)

        reader = FakeExecutionReader(
            None
        )

        service = self.make_service(
            reader
        )

        result = service.confirm_if_filled(
            position_id=state.position_id,
            broker_order_id="broker-order-1",
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
        )

        self.assertIsNone(
            result
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.CLOSING,
        )

        self.assertEqual(
            persisted.remaining_quantity,
            Decimal("1"),
        )

        self.assertEqual(
            persisted.version,
            state.version,
        )

    def test_active_position_cannot_be_closed(
        self,
    ) -> None:
        state = make_state(
            status=PositionStateStatus.ACTIVE,
        )

        self.store.insert(state)

        reader = FakeExecutionReader(
            make_filled_execution()
        )

        service = self.make_service(
            reader
        )

        with self.assertRaisesRegex(
            PositionCloseConfirmationError,
            "only a closing position",
        ):
            service.confirm_if_filled(
                position_id=state.position_id,
                broker_order_id="broker-order-1",
                ref_id=(
                    "00000000-0000-4000-8000-000000000001"
                ),
            )

        self.assertEqual(
            reader.calls,
            [],
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.ACTIVE,
        )

    def test_closed_position_is_idempotent(
        self,
    ) -> None:
        state = replace(
            make_state(),
            status=PositionStateStatus.CLOSED,
            remaining_quantity=Decimal("0"),
        )

        self.store.insert(state)

        reader = FakeExecutionReader(
            make_filled_execution()
        )

        service = self.make_service(
            reader
        )

        result = service.confirm_if_filled(
            position_id=state.position_id,
            broker_order_id="broker-order-1",
            ref_id=(
                "00000000-0000-4000-8000-000000000001"
            ),
        )

        self.assertEqual(
            result,
            state,
        )

        self.assertEqual(
            reader.calls,
            [],
        )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.version,
            state.version,
        )

    def test_concurrent_state_change_prevents_stale_close(
        self,
    ) -> None:
        state = make_state()
        self.store.insert(state)

        def modify_state() -> None:
            current = self.store.get(
                state.position_id
            )

            newer = replace(
                current,
                last_reconciled_at=(
                    _NOW
                    + timedelta(seconds=30)
                ),
                version=current.version + 1,
            )

            self.store.update(
                newer,
                expected_version=current.version,
            )

        reader = FakeExecutionReader(
            make_filled_execution(),
            before_return=modify_state,
        )

        service = self.make_service(
            reader
        )

        with self.assertRaises(
            ConcurrentStateUpdateError
        ):
            service.confirm_if_filled(
                position_id=state.position_id,
                broker_order_id="broker-order-1",
                ref_id=(
                    "00000000-0000-4000-8000-000000000001"
                ),
            )

        persisted = self.store.get(
            state.position_id
        )

        self.assertEqual(
            persisted.status,
            PositionStateStatus.CLOSING,
        )

        self.assertEqual(
            persisted.version,
            state.version + 1,
        )


if __name__ == "__main__":
    unittest.main()