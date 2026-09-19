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
    PlacementReconciliationOutcome,
    PlacementReconciliationStatus,
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
    RECOVERED = "recovered"
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

@dataclass(frozen=True)
class PlacementRecoveryEvidence:
    broker_order_id: str
    recovered_at: datetime

    def __post_init__(self) -> None:
        if not self.broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if (
            self.recovered_at.tzinfo is None
            or self.recovered_at.utcoffset() is None
        ):
            raise ValueError(
                "recovered_at must be timezone-aware"
            )

class PlacementAttemptStateConflictError(RuntimeError):
    pass

class PlacementReconciliationObservationAlreadyExistsError(
    RuntimeError
):
    pass


class PlacementAttemptNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlacementReconciliationObservationRecord:
    ref_id: str
    status: PlacementReconciliationStatus
    checked_at: datetime
    broker_order_id: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        if (
            self.checked_at.tzinfo is None
            or self.checked_at.utcoffset() is None
        ):
            raise ValueError(
                "checked_at must be timezone-aware"
            )

        if (
            self.status
            is PlacementReconciliationStatus.FOUND
        ):
            if (
                self.broker_order_id is None
                or not self.broker_order_id.strip()
            ):
                raise ValueError(
                    "found observation requires broker_order_id"
                )

        elif self.broker_order_id is not None:
            raise ValueError(
                "non-found observation cannot contain "
                "broker_order_id"
            )

        if (
            self.message is not None
            and not self.message.strip()
        ):
            raise ValueError(
                "message cannot be empty"
            )

def build_reconciliation_observation(
    outcome: PlacementReconciliationOutcome,
) -> PlacementReconciliationObservationRecord:
    return PlacementReconciliationObservationRecord(
        ref_id=outcome.request.ref_id,
        status=outcome.status,
        checked_at=outcome.checked_at,
        broker_order_id=outcome.broker_order_id,
        message=outcome.message,
    )

@dataclass(frozen=True)
class PlacementAttemptRecord:
    submission: RobinhoodExitSubmission
    placement_attempted_at: datetime
    status: PlacementAttemptStatus = (
        PlacementAttemptStatus.PREPARED
    )
    acknowledgement: PlacementAcknowledgement | None = None
    recovery_evidence: PlacementRecoveryEvidence | None = None

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

            if self.recovery_evidence is not None:
                raise ValueError(
                    "acknowledged placement cannot contain "
                    "recovery evidence"
                )

            return

        if (
            self.status
            is PlacementAttemptStatus.RECOVERED
        ):
            if self.recovery_evidence is None:
                raise ValueError(
                    "recovered placement requires recovery evidence"
                )

            if self.acknowledgement is not None:
                raise ValueError(
                    "recovered placement cannot contain "
                    "acknowledgement"
                )

            return

        if self.acknowledgement is not None:
            raise ValueError(
                "non-acknowledged placement cannot contain "
                "acknowledgement"
            )

        if self.recovery_evidence is not None:
            raise ValueError(
                "non-recovered placement cannot contain "
                "recovery evidence"
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

    def list_unresolved(
        self,
    ) -> list[PlacementAttemptRecord]:
        ...

    def list_resolved(
        self,
    ) -> list[PlacementAttemptRecord]:
        ...

    def recover_found(
        self,
        ref_id: str,
        evidence: PlacementRecoveryEvidence,
    ) -> None:
        ...

    def append_reconciliation_observation(
        self,
        observation: PlacementReconciliationObservationRecord,
    ) -> None:
        ...

    def list_reconciliation_observations(
        self,
        ref_id: str,
    ) -> list[PlacementReconciliationObservationRecord]:
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

def _decode_placement_attempt_row(
    row: tuple[Any, ...],
) -> PlacementAttemptRecord:
    (
        submission_json,
        placement_attempted_at_raw,
        status_raw,
        broker_order_id,
        acknowledged_at_raw,
        recovered_broker_order_id,
        recovered_at_raw,
    ) = row

    if (
        (broker_order_id is None)
        != (acknowledged_at_raw is None)
    ):
        raise ValueError(
            "placement acknowledgement is incomplete"
        )

    if (
        (recovered_broker_order_id is None)
        != (recovered_at_raw is None)
    ):
        raise ValueError(
            "placement recovery evidence is incomplete"
        )

    acknowledgement = None

    if broker_order_id is not None:
        acknowledgement = PlacementAcknowledgement(
            broker_order_id=broker_order_id,
            acknowledged_at=datetime.fromisoformat(
                acknowledged_at_raw
            ),
        )

    recovery_evidence = None

    if recovered_broker_order_id is not None:
        recovery_evidence = PlacementRecoveryEvidence(
            broker_order_id=recovered_broker_order_id,
            recovered_at=datetime.fromisoformat(
                recovered_at_raw
            ),
        )

    return PlacementAttemptRecord(
        submission=_decode_submission(
            json.loads(submission_json)
        ),
        placement_attempted_at=datetime.fromisoformat(
            placement_attempted_at_raw
        ),
        status=PlacementAttemptStatus(
            status_raw
        ),
        acknowledgement=acknowledgement,
        recovery_evidence=recovery_evidence,
    )

class SQLitePlacementAttemptJournal:
    def __init__(
        self,
        database_path: str | Path,
    ) -> None:
        self._database_path = str(
            database_path
        )

    def _connect(
        self,
    ) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=10.0,
        )

        connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        connection.execute(
            "PRAGMA synchronous=FULL"
        )

        return connection

    def initialize(
        self,
    ) -> None:
        with closing(
            self._connect()
        ) as connection:
            with connection:
                
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS placement_attempts (
                        ref_id TEXT PRIMARY KEY,
                        submission_json TEXT NOT NULL,
                        placement_attempted_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'prepared',
                        broker_order_id TEXT,
                        acknowledged_at TEXT,
                        recovered_broker_order_id TEXT,
                        recovered_at TEXT
                    )
                    """
                )

    
                columns = {
                    row[1]
                    for row in connection.execute(
                        """
                        PRAGMA table_info(
                            placement_attempts
                        )
                        """
                    )
                }

                if "status" not in columns:
                    connection.execute(
                        """
                        ALTER TABLE placement_attempts
                        ADD COLUMN status TEXT
                        NOT NULL DEFAULT 'prepared'
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

                if (
                    "recovered_broker_order_id"
                    not in columns
                ):
                    connection.execute(
                        """
                        ALTER TABLE placement_attempts
                        ADD COLUMN
                        recovered_broker_order_id TEXT
                        """
                    )

                if "recovered_at" not in columns:
                    connection.execute(
                        """
                        ALTER TABLE placement_attempts
                        ADD COLUMN recovered_at TEXT
                        """
                    )

                
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                    placement_reconciliation_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ref_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        checked_at TEXT NOT NULL,
                        broker_order_id TEXT,
                        message TEXT,
                        UNIQUE(ref_id, checked_at),
                        FOREIGN KEY(ref_id)
                            REFERENCES placement_attempts(ref_id)
                    )
                    """
                )

    def insert(
        self,
        record: PlacementAttemptRecord,
    ) -> None:
        if (
            record.status
            is not PlacementAttemptStatus.PREPARED
        ):
            raise ValueError(
                "new placement attempt must be prepared"
            )

        if record.acknowledgement is not None:
            raise ValueError(
                "new placement attempt cannot be acknowledged"
            )

        if record.recovery_evidence is not None:
            raise ValueError(
                "new placement attempt cannot contain "
                "recovery evidence"
            )

        submission_json = json.dumps(
            asdict(
                record.submission
            ),
            default=_json_default,
            sort_keys=True,
            separators=(",", ":"),
        )

        with closing(
            self._connect()
        ) as connection:
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
                            acknowledged_at,
                            recovered_broker_order_id,
                            recovered_at
                        )
                        VALUES (
                            ?, ?, ?, ?,
                            NULL, NULL, NULL, NULL
                        )
                        """,
                        (
                            record.submission.ref_id,
                            submission_json,
                            (
                                record
                                .placement_attempted_at
                                .isoformat()
                            ),
                            record.status.value,
                        ),
                    )

            except sqlite3.IntegrityError as exc:
                raise (
                    PlacementAttemptAlreadyExistsError(
                        "placement attempt ref_id "
                        "already exists"
                    )
                ) from exc

    def get(
        self,
        ref_id: str,
    ) -> PlacementAttemptRecord | None:
        with closing(
            self._connect()
        ) as connection:
            row = connection.execute(
                """
                SELECT
                    submission_json,
                    placement_attempted_at,
                    status,
                    broker_order_id,
                    acknowledged_at,
                    recovered_broker_order_id,
                    recovered_at
                FROM placement_attempts
                WHERE ref_id = ?
                """,
                (
                    ref_id,
                ),
            ).fetchone()

        if row is None:
            return None

        return _decode_placement_attempt_row(
            row
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

        if (
            expected_status,
            new_status,
        ) not in allowed:
            raise ValueError(
                "invalid placement attempt "
                "state transition"
            )

        with closing(
            self._connect()
        ) as connection:
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
                    raise (
                        PlacementAttemptStateConflictError(
                            "placement attempt is missing "
                            "or its status has changed"
                        )
                    )

    def acknowledge(
        self,
        ref_id: str,
        acknowledgement: PlacementAcknowledgement,
    ) -> None:
        with closing(
            self._connect()
        ) as connection:
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
                      AND recovered_broker_order_id IS NULL
                      AND recovered_at IS NULL
                    """,
                    (
                        (
                            PlacementAttemptStatus
                            .ACKNOWLEDGED
                            .value
                        ),
                        acknowledgement.broker_order_id,
                        (
                            acknowledgement
                            .acknowledged_at
                            .isoformat()
                        ),
                        ref_id,
                        (
                            PlacementAttemptStatus
                            .SUBMITTING
                            .value
                        ),
                    ),
                )

                if cursor.rowcount != 1:
                    raise (
                        PlacementAttemptStateConflictError(
                            "placement attempt cannot "
                            "be acknowledged from "
                            "its current state"
                        )
                    )

    def list_unresolved(
        self,
    ) -> list[PlacementAttemptRecord]:
        unresolved_statuses = (
            PlacementAttemptStatus.PREPARED.value,
            PlacementAttemptStatus.SUBMITTING.value,
            PlacementAttemptStatus.UNCERTAIN.value,
        )

        with closing(
            self._connect()
        ) as connection:
            rows = connection.execute(
                """
                SELECT
                    submission_json,
                    placement_attempted_at,
                    status,
                    broker_order_id,
                    acknowledged_at,
                    recovered_broker_order_id,
                    recovered_at
                FROM placement_attempts
                WHERE status IN (?, ?, ?)
                ORDER BY
                    placement_attempted_at ASC,
                    ref_id ASC
                """,
                unresolved_statuses,
            ).fetchall()

        return [
            _decode_placement_attempt_row(
                row
            )
            for row in rows
        ]

    def list_resolved(
        self,
    ) -> list[PlacementAttemptRecord]:
        resolved_statuses = (
            PlacementAttemptStatus.ACKNOWLEDGED.value,
            PlacementAttemptStatus.RECOVERED.value,
        )

        with closing(
            self._connect()
        ) as connection:
            rows = connection.execute(
                """
                SELECT
                    submission_json,
                    placement_attempted_at,
                    status,
                    broker_order_id,
                    acknowledged_at,
                    recovered_broker_order_id,
                    recovered_at
                FROM placement_attempts
                WHERE status IN (?, ?)
                ORDER BY
                    placement_attempted_at ASC,
                    ref_id ASC
                """,
                resolved_statuses,
            ).fetchall()

        return [
            _decode_placement_attempt_row(
                row
            )
            for row in rows
        ]

    def recover_found(
        self,
        ref_id: str,
        evidence: PlacementRecoveryEvidence,
    ) -> None:
        recoverable_statuses = (
            PlacementAttemptStatus.PREPARED.value,
            PlacementAttemptStatus.SUBMITTING.value,
            PlacementAttemptStatus.UNCERTAIN.value,
        )

        with closing(
            self._connect()
        ) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE placement_attempts
                    SET
                        status = ?,
                        recovered_broker_order_id = ?,
                        recovered_at = ?
                    WHERE ref_id = ?
                      AND status IN (?, ?, ?)
                      AND broker_order_id IS NULL
                      AND acknowledged_at IS NULL
                      AND recovered_broker_order_id IS NULL
                      AND recovered_at IS NULL
                    """,
                    (
                        (
                            PlacementAttemptStatus
                            .RECOVERED
                            .value
                        ),
                        evidence.broker_order_id,
                        evidence.recovered_at.isoformat(),
                        ref_id,
                        *recoverable_statuses,
                    ),
                )

                if cursor.rowcount != 1:
                    raise (
                        PlacementAttemptStateConflictError(
                            "placement attempt cannot "
                            "be recovered from "
                            "its current state"
                        )
                    )

    def append_reconciliation_observation(
        self,
        observation: PlacementReconciliationObservationRecord,
    ) -> None:
        with closing(
            self._connect()
        ) as connection:
            try:
                with connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO
                        placement_reconciliation_observations (
                            ref_id,
                            status,
                            checked_at,
                            broker_order_id,
                            message
                        )
                        SELECT
                            ?, ?, ?, ?, ?
                        WHERE EXISTS (
                            SELECT 1
                            FROM placement_attempts
                            WHERE ref_id = ?
                        )
                        """,
                        (
                            observation.ref_id,
                            observation.status.value,
                            observation.checked_at.isoformat(),
                            observation.broker_order_id,
                            observation.message,
                            observation.ref_id,
                        ),
                    )

                    if cursor.rowcount != 1:
                        raise PlacementAttemptNotFoundError(
                            "placement attempt does not exist"
                        )

            except sqlite3.IntegrityError as exc:
                raise (
                    PlacementReconciliationObservationAlreadyExistsError(
                        "reconciliation observation already exists"
                    )
                ) from exc

    def list_reconciliation_observations(
        self,
        ref_id: str,
    ) -> list[PlacementReconciliationObservationRecord]:
        with closing(
            self._connect()
        ) as connection:
            rows = connection.execute(
                """
                SELECT
                    ref_id,
                    status,
                    checked_at,
                    broker_order_id,
                    message
                FROM placement_reconciliation_observations
                WHERE ref_id = ?
                ORDER BY
                    checked_at ASC,
                    id ASC
                """,
                (
                    ref_id,
                ),
            ).fetchall()

        return [
            PlacementReconciliationObservationRecord(
                ref_id=row[0],
                status=PlacementReconciliationStatus(
                    row[1]
                ),
                checked_at=datetime.fromisoformat(
                    row[2]
                ),
                broker_order_id=row[3],
                message=row[4],
            )
            for row in rows
        ]