import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from stock_agent.brokers.robinhood.entry_review import (
    RobinhoodEquityEntryReview,
    build_robinhood_equity_entry_review_arguments,
    revalidate_robinhood_equity_entry_review,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)


class EntryPlacementStatus(StrEnum):
    PREPARED = "prepared"
    SUBMITTING = "submitting"
    ACKNOWLEDGED = "acknowledged"
    UNCERTAIN = "uncertain"
    ACTIVATED = "activated"

class RobinhoodEquityEntryPlacementUncertainError(
    RuntimeError
):
    def __init__(
        self,
        *,
        ref_id: str,
    ) -> None:
        super().__init__(
            "Robinhood equity entry placement "
            "outcome is uncertain"
        )
        self.ref_id = ref_id


@dataclass(frozen=True, slots=True)
class EquityEntryPlacementRecord:
    ref_id: str
    account_number: str
    symbol: str
    arguments: dict[str, str]
    attempted_at: datetime
    status: EntryPlacementStatus
    broker_order_id: str | None = None
    acknowledged_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        if not self.account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if (
            self.attempted_at.tzinfo is None
            or self.attempted_at.utcoffset()
            is None
        ):
            raise ValueError(
                "attempted_at must be timezone-aware"
            )

        if self.status in {
            EntryPlacementStatus.ACKNOWLEDGED,
            EntryPlacementStatus.ACTIVATED,
        }:
            if (
                self.broker_order_id is None
                or not self.broker_order_id.strip()
            ):
                raise ValueError(
                    "acknowledged placement requires "
                    "broker_order_id"
                )

            if self.acknowledged_at is None:
                raise ValueError(
                    "acknowledged placement requires "
                    "acknowledged_at"
                )

        elif (
            self.broker_order_id is not None
            or self.acknowledged_at is not None
        ):
            raise ValueError(
                "non-acknowledged placement cannot "
                "contain acknowledgement"
            )


@dataclass(frozen=True, slots=True)
class RobinhoodEquityEntryPlacementResult:
    ref_id: str
    broker_order_id: str
    submitted_at: datetime


class SQLiteEquityEntryPlacementJournal:
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
                    CREATE TABLE IF NOT EXISTS
                    entry_placement_attempts (
                        ref_id TEXT PRIMARY KEY,
                        account_number TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        arguments_json TEXT NOT NULL,
                        attempted_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        broker_order_id TEXT,
                        acknowledged_at TEXT
                    )
                    """
                )

    def insert(
        self,
        record: EquityEntryPlacementRecord,
    ) -> None:
        with closing(
            self._connect()
        ) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO
                    entry_placement_attempts (
                        ref_id,
                        account_number,
                        symbol,
                        arguments_json,
                        attempted_at,
                        status,
                        broker_order_id,
                        acknowledged_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.ref_id,
                        record.account_number,
                        record.symbol,
                        json.dumps(
                            record.arguments,
                            sort_keys=True,
                        ),
                        record.attempted_at.isoformat(),
                        record.status.value,
                        record.broker_order_id,
                        (
                            record.acknowledged_at
                            .isoformat()
                            if record.acknowledged_at
                            is not None
                            else None
                        ),
                    ),
                )

    def transition(
        self,
        ref_id: str,
        *,
        expected_status: EntryPlacementStatus,
        new_status: EntryPlacementStatus,
    ) -> None:
        with closing(
            self._connect()
        ) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE entry_placement_attempts
                    SET status = ?
                    WHERE
                        ref_id = ?
                        AND status = ?
                    """,
                    (
                        new_status.value,
                        ref_id,
                        expected_status.value,
                    ),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "entry placement journal "
                        "state transition failed"
                    )

    def acknowledge(
        self,
        ref_id: str,
        *,
        broker_order_id: str,
        acknowledged_at: datetime,
    ) -> None:
        with closing(
            self._connect()
        ) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE entry_placement_attempts
                    SET
                        status = ?,
                        broker_order_id = ?,
                        acknowledged_at = ?
                    WHERE
                        ref_id = ?
                        AND status = ?
                    """,
                    (
                        EntryPlacementStatus
                        .ACKNOWLEDGED.value,
                        broker_order_id,
                        acknowledged_at.isoformat(),
                        ref_id,
                        EntryPlacementStatus
                        .SUBMITTING.value,
                    ),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "entry placement acknowledgement "
                        "failed"
                    )

    def get(
        self,
        ref_id: str,
    ) -> EquityEntryPlacementRecord | None:
        with closing(
            self._connect()
        ) as connection:
            row = connection.execute(
                """
                SELECT
                    ref_id,
                    account_number,
                    symbol,
                    arguments_json,
                    attempted_at,
                    status,
                    broker_order_id,
                    acknowledged_at
                FROM entry_placement_attempts
                WHERE ref_id = ?
                """,
                (ref_id,),
            ).fetchone()

        if row is None:
            return None

        (
            stored_ref_id,
            account_number,
            symbol,
            arguments_json,
            attempted_at,
            status,
            broker_order_id,
            acknowledged_at,
        ) = row

        return EquityEntryPlacementRecord(
            ref_id=stored_ref_id,
            account_number=account_number,
            symbol=symbol,
            arguments=json.loads(
                arguments_json
            ),
            attempted_at=datetime.fromisoformat(
                attempted_at
            ),
            status=EntryPlacementStatus(
                status
            ),
            broker_order_id=broker_order_id,
            acknowledged_at=(
                datetime.fromisoformat(
                    acknowledged_at
                )
                if acknowledged_at is not None
                else None
            ),
        )

    def list_acknowledged(
        self,
        *,
        account_number: str,
    ) -> list[EquityEntryPlacementRecord]:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        with closing(
            self._connect()
        ) as connection:
            rows = connection.execute(
                """
                SELECT
                    ref_id,
                    account_number,
                    symbol,
                    arguments_json,
                    attempted_at,
                    status,
                    broker_order_id,
                    acknowledged_at
                FROM entry_placement_attempts
                WHERE
                    account_number = ?
                    AND status = ?
                ORDER BY
                    attempted_at,
                    ref_id
                """,
                (
                    account_number,
                    EntryPlacementStatus
                    .ACKNOWLEDGED.value,
                ),
            ).fetchall()

        records = []

        for row in rows:
            (
                ref_id,
                stored_account_number,
                symbol,
                arguments_json,
                attempted_at,
                status,
                broker_order_id,
                acknowledged_at,
            ) = row

            records.append(
                EquityEntryPlacementRecord(
                    ref_id=ref_id,
                    account_number=(
                        stored_account_number
                    ),
                    symbol=symbol,
                    arguments=json.loads(
                        arguments_json
                    ),
                    attempted_at=(
                        datetime.fromisoformat(
                            attempted_at
                        )
                    ),
                    status=(
                        EntryPlacementStatus(
                            status
                        )
                    ),
                    broker_order_id=(
                        broker_order_id
                    ),
                    acknowledged_at=(
                        datetime.fromisoformat(
                            acknowledged_at
                        )
                        if acknowledged_at
                        is not None
                        else None
                    ),
                )
            )

        return records


def _decode_entry_placement_result(
    raw_result: Any,
    *,
    ref_id: str,
    submitted_at: datetime,
) -> RobinhoodEquityEntryPlacementResult:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood placement result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood placement result "
            "must contain data"
        )

    order = data.get(
        "order"
    )

    if not isinstance(
        order,
        dict,
    ):
        raise ValueError(
            "Robinhood placement result "
            "must contain order"
        )

    broker_order_id = order.get(
        "id"
    )

    if (
        not isinstance(
            broker_order_id,
            str,
        )
        or not broker_order_id.strip()
    ):
        raise ValueError(
            "Robinhood placement order "
            "must contain id"
        )

    returned_ref_id = order.get(
        "ref_id"
    )

    if returned_ref_id != ref_id:
        raise ValueError(
            "Robinhood placement ref_id "
            "does not match request"
        )

    return RobinhoodEquityEntryPlacementResult(
        ref_id=ref_id,
        broker_order_id=broker_order_id,
        submitted_at=submitted_at,
    )


def place_robinhood_equity_entry(
    invoker: MCPToolInvoker,
    journal: SQLiteEquityEntryPlacementJournal,
    *,
    account_number: str,
    review: RobinhoodEquityEntryReview,
    clock: Callable[[], datetime],
    ref_id_factory: Callable[[], str] | None = None,
) -> RobinhoodEquityEntryPlacementResult:
    now = clock()

    # Revalidate the broker's live quote immediately
    # before crossing the placement boundary.
    revalidate_robinhood_equity_entry_review(
        review,
        evaluated_at=now,
    )

    ref_id = (
        ref_id_factory
        or (lambda: str(uuid4()))
    )()

    review_arguments = (
        build_robinhood_equity_entry_review_arguments(
            review.plan,
            account_number=account_number,
        )
    )

    placement_arguments = {
        **review_arguments,
        "ref_id": ref_id,
    }

    journal.insert(
        EquityEntryPlacementRecord(
            ref_id=ref_id,
            account_number=account_number,
            symbol=review.plan.symbol,
            arguments=placement_arguments,
            attempted_at=now,
            status=(
                EntryPlacementStatus.PREPARED
            ),
        )
    )

    journal.transition(
        ref_id,
        expected_status=(
            EntryPlacementStatus.PREPARED
        ),
        new_status=(
            EntryPlacementStatus.SUBMITTING
        ),
    )

    try:
        raw_result = invoker.call_tool(
            "place_equity_order",
            placement_arguments,
        )
    except Exception as error:
        journal.transition(
            ref_id,
            expected_status=(
                EntryPlacementStatus.SUBMITTING
            ),
            new_status=(
                EntryPlacementStatus.UNCERTAIN
            ),
        )

        raise (
            RobinhoodEquityEntryPlacementUncertainError(
                ref_id=ref_id
            )
        ) from error

    submitted_at = clock()

    try:
        result = _decode_entry_placement_result(
            raw_result,
            ref_id=ref_id,
            submitted_at=submitted_at,
        )
    except Exception as error:
        # Broker side effect may already have happened.
        journal.transition(
            ref_id,
            expected_status=(
                EntryPlacementStatus.SUBMITTING
            ),
            new_status=(
                EntryPlacementStatus.UNCERTAIN
            ),
        )

        raise (
            RobinhoodEquityEntryPlacementUncertainError(
                ref_id=ref_id
            )
        ) from error

    journal.acknowledge(
        ref_id,
        broker_order_id=(
            result.broker_order_id
        ),
        acknowledged_at=submitted_at,
    )

    return result