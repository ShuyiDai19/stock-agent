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
    ACKNOWLEDGED = "acknowledged"
    NOT_SENT = "not_sent"
    UNCERTAIN = "uncertain"

@dataclass(frozen=True)
class PlacementAcknowledgement:
    broker_order_id: str
    acknowledged_at: datetime

    def __post_init__(self) -> None:
        if not self.broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if (
            self.acknowledged_at.tzinfo is None
            or self.acknowledged_at.utcoffset() is None
        ):
            raise ValueError(
                "acknowledged_at must be timezone-aware"
            )

class PlacementAttemptStateConflictError(RuntimeError):
    pass

@dataclass(frozen=True)
class PlacementAttemptRecord:
    submission: RobinhoodExitSubmission
    placement_attempted_at: datetime
    status: PlacementAttemptStatus = (
        PlacementAttemptStatus.PREPARED
    )
    acknowledgement: PlacementAcknowledgement | None = None

    def __post_init__(self) -> None:
        build_placement_reconciliation_request(
            self.submission,
            placement_attempted_at=self.placement_attempted_at,
        )

        if not isinstance(
            self.status,
            PlacementAttemptStatus,
        ):
            raise ValueError(
                "invalid placement attempt status"
            )

        if (
            self.status
            is PlacementAttemptStatus.ACKNOWLEDGED
        ):
            if self.acknowledgement is None:
                raise ValueError(
                    "acknowledged placement requires acknowledgement"
                )
        elif self.acknowledgement is not None:
            raise ValueError(
                "non-acknowledged placement cannot contain acknowledgement"
            )

class PlacementAttemptJournal(Protocol):
    def insert(
        self,
        record: PlacementAttemptRecord,
    ) -> None:
        ...

    def transition(
        self,
        ref_id: str,
        *,
        expected_status: PlacementAttemptStatus,
        new_status: PlacementAttemptStatus,
    ) -> None:
        ...

    def acknowledge(
        self,
        ref_id: str,
        acknowledgement: PlacementAcknowledgement,
    ) -> None:
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
                        status TEXT NOT NULL DEFAULT 'prepared',
                        broker_order_id TEXT,
                        acknowledged_at TEXT
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

                if "broker_order_id" not in columns:
                    connection.execute(
                        """
                        ALTER TABLE placement_attempts
                        ADD COLUMN broker_order_id TEXT
                        """
                    )

                if "acknowledged_at" not in columns:
                    connection.execute(
                        """
                        ALTER TABLE placement_attempts
                        ADD COLUMN acknowledged_at TEXT
                        """
                    )

    def insert(self, record: PlacementAttemptRecord) -> None:
        if record.status is not PlacementAttemptStatus.PREPARED:
            raise ValueError(
                "new placement attempt must be prepared"
            )

        if record.acknowledgement is not None:
            raise ValueError(
                "new placement attempt cannot be acknowledged"
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
                            status,
                            broker_order_id,
                            acknowledged_at
                        ) VALUES (?, ?, ?, ?, NULL, NULL)
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
                SELECT
                    submission_json,
                    placement_attempted_at,
                    status,
                    broker_order_id,
                    acknowledged_at
                FROM placement_attempts
                WHERE ref_id = ?
                """,
                (ref_id,),
            ).fetchone()

        if row is None:
            return None

        broker_order_id = row[3]
        acknowledged_at_raw = row[4]

        if (
            (broker_order_id is None)
            != (acknowledged_at_raw is None)
        ):
            raise ValueError(
                "placement acknowledgement is incomplete"
            )

        acknowledgement = None

        if broker_order_id is not None:
            acknowledgement = PlacementAcknowledgement(
                broker_order_id=broker_order_id,
                acknowledged_at=datetime.fromisoformat(
                    acknowledged_at_raw
                ),
            )

        return PlacementAttemptRecord(
            submission=_decode_submission(
                json.loads(row[0])
            ),
            placement_attempted_at=datetime.fromisoformat(
                row[1]
            ),
            status=PlacementAttemptStatus(row[2]),
            acknowledgement=acknowledgement,
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
                PlacementAttemptStatus.NOT_SENT,
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

    def acknowledge(
        self,
        ref_id: str,
        acknowledgement: PlacementAcknowledgement,
    ) -> None:
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE placement_attempts
                    SET
                        status = ?,
                        broker_order_id = ?,
                        acknowledged_at = ?
                    WHERE ref_id = ?
                    AND status = ?
                    AND broker_order_id IS NULL
                    AND acknowledged_at IS NULL
                    """,
                    (
                        PlacementAttemptStatus.ACKNOWLEDGED.value,
                        acknowledgement.broker_order_id,
                        acknowledgement.acknowledged_at.isoformat(),
                        ref_id,
                        PlacementAttemptStatus.SUBMITTING.value,
                    ),
                )

                if cursor.rowcount != 1:
                    raise PlacementAttemptStateConflictError(
                        "placement attempt cannot be acknowledged "
                        "from its current state"
                    )