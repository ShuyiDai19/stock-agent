import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Protocol

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.reconciliation import (
    build_placement_reconciliation_request,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodMarketHours,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.domain import AssetType


class PlacementAttemptAlreadyExistsError(RuntimeError):
    pass

class PlacementAttemptStatus(str, Enum):
    PREPARED = "prepared"
    SUBMITTING = "submitting"
    UNCERTAIN = "uncertain"


class PlacementAttemptStateConflictError(RuntimeError):
    pass

@dataclass(frozen=True)
class PlacementAttemptRecord:
    submission: RobinhoodExitSubmission
    placement_attempted_at: datetime
    status: PlacementAttemptStatus = PlacementAttemptStatus.PREPARED

    def __post_init__(self) -> None:
        build_placement_reconciliation_request(
            self.submission,
            placement_attempted_at=self.placement_attempted_at,
        )

        if not isinstance(self.status, PlacementAttemptStatus):
            raise ValueError("invalid placement attempt status")

class PlacementAttemptJournal(Protocol):
    def insert(self, record: PlacementAttemptRecord) -> None:
        ...


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


def _decode_submission(payload: dict[str, Any]) -> RobinhoodExitSubmission:
    request = payload["request"]
    limit_price = payload["limit_price"]

    return RobinhoodExitSubmission(
        request=RobinhoodExitOrderRequest(
            position_id=request["position_id"],
            account_number=request["account_number"],
            asset_type=AssetType(request["asset_type"]),
            symbol=request["symbol"],
            quantity=Decimal(request["quantity"]),
            action=RobinhoodExitAction(request["action"]),
            option_id=request["option_id"],
        ),
        ref_id=payload["ref_id"],
        order_type=RobinhoodOrderType(payload["order_type"]),
        time_in_force=RobinhoodTimeInForce(
            payload["time_in_force"]
        ),
        market_hours=RobinhoodMarketHours(
            payload["market_hours"]
        ),
        limit_price=(
            Decimal(limit_price)
            if limit_price is not None
            else None
        ),
    )


class SQLitePlacementAttemptJournal:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=10.0,
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS placement_attempts (
                        ref_id TEXT PRIMARY KEY,
                        submission_json TEXT NOT NULL,
                        placement_attempted_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'prepared'
                    )
                    """
                )

                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(placement_attempts)"
                    )
                }

                if "status" not in columns:
                    connection.execute(
                        """
                        ALTER TABLE placement_attempts
                        ADD COLUMN status TEXT NOT NULL DEFAULT 'prepared'
                        """
                    )

    def insert(self, record: PlacementAttemptRecord) -> None:
        if record.status is not PlacementAttemptStatus.PREPARED:
            raise ValueError(
                "new placement attempt must be prepared"
            )
        
        submission_json = json.dumps(
            asdict(record.submission),
            default=_json_default,
            sort_keys=True,
            separators=(",", ":"),
        )

        with closing(self._connect()) as connection:
            try:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO placement_attempts (
                            ref_id,
                            submission_json,
                            placement_attempted_at,
                            status
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            record.submission.ref_id,
                            submission_json,
                            record.placement_attempted_at.isoformat(),
                            record.status.value,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise PlacementAttemptAlreadyExistsError(
                    "placement attempt ref_id already exists"
                ) from exc

    def get(self, ref_id: str) -> PlacementAttemptRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT submission_json, placement_attempted_at, status
                FROM placement_attempts
                WHERE ref_id = ?
                """,
                (ref_id,),
            ).fetchone()

        if row is None:
            return None

        return PlacementAttemptRecord(
            submission=_decode_submission(json.loads(row[0])),
            placement_attempted_at=datetime.fromisoformat(row[1]),
            status=PlacementAttemptStatus(row[2]),
        )

    def transition(
        self,
        ref_id: str,
        *,
        expected_status: PlacementAttemptStatus,
        new_status: PlacementAttemptStatus,
    ) -> None:
        allowed = {
            (
                PlacementAttemptStatus.PREPARED,
                PlacementAttemptStatus.SUBMITTING,
            ),
            (
                PlacementAttemptStatus.PREPARED,
                PlacementAttemptStatus.UNCERTAIN,
            ),
            (
                PlacementAttemptStatus.SUBMITTING,
                PlacementAttemptStatus.UNCERTAIN,
            ),
        }

        if (expected_status, new_status) not in allowed:
            raise ValueError(
                "invalid placement attempt state transition"
            )

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE placement_attempts
                    SET status = ?
                    WHERE ref_id = ?
                    AND status = ?
                    """,
                    (
                        new_status.value,
                        ref_id,
                        expected_status.value,
                    ),
                )

                if cursor.rowcount != 1:
                    raise PlacementAttemptStateConflictError(
                        "placement attempt is missing or "
                        "its status has changed"
                    )