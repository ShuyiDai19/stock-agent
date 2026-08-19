from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ExecutionStatus(str, Enum):
    SUBMITTED = "submitted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ExecutionResult:
    position_id: str
    status: ExecutionStatus
    submitted_at: datetime
    broker_order_id: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.position_id.strip():
            raise ValueError("position_id cannot be empty")

        if (
            self.submitted_at.tzinfo is None
            or self.submitted_at.utcoffset() is None
        ):
            raise ValueError(
                "submitted_at must be timezone-aware"
            )

        if (
            self.status is ExecutionStatus.SUBMITTED
            and (
                self.broker_order_id is None
                or not self.broker_order_id.strip()
            )
        ):
            raise ValueError(
                "submitted execution must have broker_order_id"
            )