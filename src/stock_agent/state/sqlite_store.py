import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)
from stock_agent.state.store import (
    ConcurrentStateUpdateError,
    PositionStateAlreadyExistsError,
    PositionStateNotFoundError,
)

_SCHEMA_VERSION = 1


class SQLitePositionStateStore:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    @property
    def database_path(self) -> Path:
        return self._database_path

    def initialize(self) -> None:
        """
        Create the state database and required tables.

        This operation is idempotent and may safely run at every process
        startup.
        """
        self._database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection = self._connect()

        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS position_state (
                    position_id TEXT PRIMARY KEY,
                    account_number TEXT NOT NULL,
                    asset_type TEXT NOT NULL
                        CHECK (asset_type IN ('equity', 'option')),
                    symbol TEXT NOT NULL,
                    opening_order_id TEXT NOT NULL,

                    entry_price TEXT NOT NULL,
                    remaining_quantity TEXT NOT NULL,
                    opened_at TEXT NOT NULL,

                    highest_executable_bid TEXT NOT NULL,
                    trailing_armed INTEGER NOT NULL
                        CHECK (trailing_armed IN (0, 1)),
                    trailing_armed_at TEXT,
                    activation_gain_ratio TEXT NOT NULL,
                    drawdown_ratio TEXT NOT NULL,

                    last_quote_at TEXT NOT NULL,
                    last_reconciled_at TEXT NOT NULL,

                    status TEXT NOT NULL
                        CHECK (
                            status IN (
                                'active',
                                'closing',
                                'closed',
                                'reconciliation_required'
                            )
                        ),

                    option_id TEXT,
                    historical_high_unknown INTEGER NOT NULL DEFAULT 0
                        CHECK (historical_high_unknown IN (0, 1)),
                    version INTEGER NOT NULL
                        CHECK (version >= 1),

                    UNIQUE (account_number, opening_order_id),

                    CHECK (
                        (
                            asset_type = 'equity'
                            AND option_id IS NULL
                        )
                        OR
                        (
                            asset_type = 'option'
                            AND option_id IS NOT NULL
                        )
                    ),

                    CHECK (
                        (
                            trailing_armed = 1
                            AND trailing_armed_at IS NOT NULL
                        )
                        OR
                        (
                            trailing_armed = 0
                            AND trailing_armed_at IS NULL
                        )
                    )
                );

                CREATE INDEX IF NOT EXISTS
                    idx_position_state_account_status
                ON position_state (
                    account_number,
                    status
                );

                CREATE INDEX IF NOT EXISTS
                    idx_position_state_symbol
                ON position_state (
                    account_number,
                    symbol,
                    asset_type
                );
                """
            )

            connection.execute(
                f"PRAGMA user_version = {_SCHEMA_VERSION}"
            )
            connection.commit()
        finally:
            connection.close()
    
    def insert(self, state: PositionRuntimeState) -> None:
        connection = self._connect()

        try:
            connection.execute("BEGIN IMMEDIATE")

            try:
                connection.execute(
                    """
                    INSERT INTO position_state (
                        position_id,
                        account_number,
                        asset_type,
                        symbol,
                        opening_order_id,
                        entry_price,
                        remaining_quantity,
                        opened_at,
                        highest_executable_bid,
                        trailing_armed,
                        trailing_armed_at,
                        activation_gain_ratio,
                        drawdown_ratio,
                        last_quote_at,
                        last_reconciled_at,
                        status,
                        option_id,
                        historical_high_unknown,
                        version
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        state.position_id,
                        state.account_number,
                        state.asset_type.value,
                        state.symbol,
                        state.opening_order_id,
                        str(state.entry_price),
                        str(state.remaining_quantity),
                        state.opened_at.isoformat(),
                        str(state.highest_executable_bid),
                        int(state.trailing_armed),
                        (
                            state.trailing_armed_at.isoformat()
                            if state.trailing_armed_at is not None
                            else None
                        ),
                        str(state.activation_gain_ratio),
                        str(state.drawdown_ratio),
                        state.last_quote_at.isoformat(),
                        state.last_reconciled_at.isoformat(),
                        state.status.value,
                        state.option_id,
                        int(state.historical_high_unknown),
                        state.version,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise PositionStateAlreadyExistsError(
                    "Position state already exists for "
                    f"{state.position_id!r}."
                ) from exc
        finally:
            connection.close()

    def get(
        self,
        position_id: str,
    ) -> PositionRuntimeState | None:
        connection = self._connect()

        try:
            row = connection.execute(
                """
                SELECT *
                FROM position_state
                WHERE position_id = ?
                """,
                (position_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._row_to_state(row)

    def update(
        self,
        state: PositionRuntimeState,
        *,
        expected_version: int,
    ) -> None:
        if expected_version < 1:
            raise ValueError("expected_version must be at least 1")

        if state.version != expected_version + 1:
            raise ValueError(
                "state.version must equal expected_version + 1"
            )

        connection = self._connect()

        try:
            connection.execute("BEGIN IMMEDIATE")

            cursor = connection.execute(
                """
                UPDATE position_state
                SET
                    account_number = ?,
                    asset_type = ?,
                    symbol = ?,
                    opening_order_id = ?,
                    entry_price = ?,
                    remaining_quantity = ?,
                    opened_at = ?,
                    highest_executable_bid = ?,
                    trailing_armed = ?,
                    trailing_armed_at = ?,
                    activation_gain_ratio = ?,
                    drawdown_ratio = ?,
                    last_quote_at = ?,
                    last_reconciled_at = ?,
                    status = ?,
                    option_id = ?,
                    historical_high_unknown = ?,
                    version = ?
                WHERE position_id = ?
                  AND version = ?
                """,
                (
                    state.account_number,
                    state.asset_type.value,
                    state.symbol,
                    state.opening_order_id,
                    str(state.entry_price),
                    str(state.remaining_quantity),
                    state.opened_at.isoformat(),
                    str(state.highest_executable_bid),
                    int(state.trailing_armed),
                    (
                        state.trailing_armed_at.isoformat()
                        if state.trailing_armed_at is not None
                        else None
                    ),
                    str(state.activation_gain_ratio),
                    str(state.drawdown_ratio),
                    state.last_quote_at.isoformat(),
                    state.last_reconciled_at.isoformat(),
                    state.status.value,
                    state.option_id,
                    int(state.historical_high_unknown),
                    state.version,
                    state.position_id,
                    expected_version,
                ),
            )

            if cursor.rowcount == 1:
                connection.commit()
                return

            exists = connection.execute(
                """
                SELECT 1
                FROM position_state
                WHERE position_id = ?
                """,
                (state.position_id,),
            ).fetchone()

            connection.rollback()

            if exists is None:
                raise PositionStateNotFoundError(
                    f"Position state {state.position_id!r} was not found."
                )

            raise ConcurrentStateUpdateError(
                "Position state was modified by another process; "
                f"expected version {expected_version}."
            )
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _row_to_state(
        row: sqlite3.Row,
    ) -> PositionRuntimeState:
        trailing_armed_at = (
            datetime.fromisoformat(row["trailing_armed_at"])
            if row["trailing_armed_at"] is not None
            else None
        )

        return PositionRuntimeState(
            position_id=row["position_id"],
            account_number=row["account_number"],
            asset_type=AssetType(row["asset_type"]),
            symbol=row["symbol"],
            opening_order_id=row["opening_order_id"],
            entry_price=Decimal(row["entry_price"]),
            remaining_quantity=Decimal(row["remaining_quantity"]),
            opened_at=datetime.fromisoformat(row["opened_at"]),
            highest_executable_bid=Decimal(
                row["highest_executable_bid"]
            ),
            trailing_armed=bool(row["trailing_armed"]),
            trailing_armed_at=trailing_armed_at,
            activation_gain_ratio=Decimal(
                row["activation_gain_ratio"]
            ),
            drawdown_ratio=Decimal(row["drawdown_ratio"]),
            last_quote_at=datetime.fromisoformat(
                row["last_quote_at"]
            ),
            last_reconciled_at=datetime.fromisoformat(
                row["last_reconciled_at"]
            ),
            status=PositionStateStatus(row["status"]),
            option_id=row["option_id"],
            historical_high_unknown=bool(
                row["historical_high_unknown"]
            ),
            version=row["version"],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row

        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")

        return connection
