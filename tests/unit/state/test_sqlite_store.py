import sqlite3
import tempfile
import unittest
from pathlib import Path

from datetime import UTC, datetime
from decimal import Decimal
from dataclasses import replace

from stock_agent.domain import AssetType
from stock_agent.state import (
    ConcurrentStateUpdateError,
    PositionRuntimeState,
    PositionStateAlreadyExistsError,
    PositionStateNotFoundError,
    PositionStateStatus,
    SQLitePositionStateStore,
)


class SQLitePositionStateStoreTests(unittest.TestCase):
    def test_initialize_creates_database_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = (
                Path(temp_dir)
                / "nested"
                / "stock_agent.db"
            )
            store = SQLitePositionStateStore(database_path)

            store.initialize()

            self.assertTrue(database_path.exists())

            connection = sqlite3.connect(database_path)

            try:
                table = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name = 'position_state'
                    """
                ).fetchone()

                schema_version = connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertIsNotNone(table)
            self.assertEqual(schema_version, 1)

    def test_initialize_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)

            store.initialize()
            store.initialize()

            connection = sqlite3.connect(database_path)

            try:
                table_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name = 'position_state'
                    """
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(table_count, 1)

    def make_state(self) -> PositionRuntimeState:
        now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)

        return PositionRuntimeState(
            position_id="test-account:equity:AAPL:order-123",
            account_number="test-account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            opening_order_id="order-123",
            entry_price=Decimal("321.66"),
            remaining_quantity=Decimal("0.031089"),
            opened_at=now,
            highest_executable_bid=Decimal("337.68"),
            trailing_armed=True,
            trailing_armed_at=now,
            activation_gain_ratio=Decimal("0.04"),
            drawdown_ratio=Decimal("0.02"),
            last_quote_at=now,
            last_reconciled_at=now,
        )

    def test_insert_persists_position_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            store.insert(self.make_state())

            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row

            try:
                row = connection.execute(
                    """
                    SELECT *
                    FROM position_state
                    WHERE position_id = ?
                    """,
                    ("test-account:equity:AAPL:order-123",),
                ).fetchone()
            finally:
                connection.close()

            self.assertIsNotNone(row)
            self.assertEqual(row["symbol"], "AAPL")
            self.assertEqual(row["entry_price"], "321.66")
            self.assertEqual(row["remaining_quantity"], "0.031089")
            self.assertEqual(row["highest_executable_bid"], "337.68")
            self.assertEqual(row["trailing_armed"], 1)
            self.assertEqual(row["version"], 1)

    def test_insert_rejects_duplicate_position_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            state = self.make_state()
            store.insert(state)

            with self.assertRaises(PositionStateAlreadyExistsError):
                store.insert(state)

    def test_get_returns_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            expected = self.make_state()
            store.insert(expected)

            actual = store.get(expected.position_id)

            self.assertEqual(actual, expected)

    def test_get_recovers_state_after_store_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"

            first_store = SQLitePositionStateStore(database_path)
            first_store.initialize()

            expected = self.make_state()
            first_store.insert(expected)

            restarted_store = SQLitePositionStateStore(database_path)
            restarted_store.initialize()

            actual = restarted_store.get(expected.position_id)

            self.assertIsNotNone(actual)
            self.assertEqual(
                actual.highest_executable_bid,
                Decimal("337.68"),
            )
            self.assertTrue(actual.trailing_armed)
            self.assertEqual(actual.version, 1)

    def test_get_returns_none_for_unknown_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            result = store.get("missing-position")

            self.assertIsNone(result)

    def test_update_persists_new_highest_bid_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            original = self.make_state()
            store.insert(original)

            updated = replace(
                original,
                highest_executable_bid=Decimal("342.50"),
                version=2,
            )

            store.update(updated, expected_version=1)

            restored = store.get(original.position_id)

            self.assertEqual(
                restored.highest_executable_bid,
                Decimal("342.50"),
            )
            self.assertEqual(restored.version, 2)

    def test_update_rejects_stale_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            original = self.make_state()
            store.insert(original)

            first_update = replace(
                original,
                highest_executable_bid=Decimal("340"),
                version=2,
            )
            store.update(first_update, expected_version=1)

            stale_update = replace(
                original,
                highest_executable_bid=Decimal("341"),
                version=2,
            )

            with self.assertRaises(ConcurrentStateUpdateError):
                store.update(stale_update, expected_version=1)

    def test_update_rejects_unknown_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            missing = replace(
                self.make_state(),
                position_id="missing-position",
                opening_order_id="missing-order",
                version=2,
            )

            with self.assertRaises(PositionStateNotFoundError):
                store.update(missing, expected_version=1)
    
    def test_list_by_status_filters_account_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()

            active = self.make_state()

            closed = replace(
                self.make_state(),
                position_id="test-account:equity:MSFT:order-456",
                symbol="MSFT",
                opening_order_id="order-456",
                remaining_quantity=Decimal("0"),
                status=PositionStateStatus.CLOSED,
            )

            other_account = replace(
                self.make_state(),
                position_id="other-account:equity:NVDA:order-789",
                account_number="other-account",
                symbol="NVDA",
                opening_order_id="order-789",
            )

            store.insert(active)
            store.insert(closed)
            store.insert(other_account)

            results = store.list_by_status(
                account_number="test-account-0000",
                statuses=(PositionStateStatus.ACTIVE,),
            )

            self.assertEqual(results, [active])

    def test_list_by_status_returns_empty_for_no_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "stock_agent.db"
            store = SQLitePositionStateStore(database_path)
            store.initialize()
            store.insert(self.make_state())

            results = store.list_by_status(
                account_number="test-account-0000",
                statuses=(),
            )

            self.assertEqual(results, [])

if __name__ == "__main__":
    unittest.main()
