from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationOutcome,
    PlacementReconciliationRequest,
    PlacementReconciliationStatus,
)


class RobinhoodOrderLookupStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RobinhoodOrderLookupResult:
    status: RobinhoodOrderLookupStatus
    broker_order_id: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status is RobinhoodOrderLookupStatus.FOUND:
            if (
                self.broker_order_id is None
                or not self.broker_order_id.strip()
            ):
                raise ValueError(
                    "found lookup requires broker_order_id"
                )
        elif self.broker_order_id is not None:
            raise ValueError(
                "non-found lookup cannot contain broker_order_id"
            )

        if (
            self.message is not None
            and not self.message.strip()
        ):
            raise ValueError(
                "message cannot be empty"
            )


class RobinhoodOrderLookup(Protocol):
    def lookup(
        self,
        request: PlacementReconciliationRequest,
    ) -> RobinhoodOrderLookupResult:
        ...


class PlacementReconciler(Protocol):
    def reconcile(
        self,
        request: PlacementReconciliationRequest,
    ) -> PlacementReconciliationOutcome:
        ...


class RobinhoodPlacementReconciler:
    def __init__(
        self,
        lookup: RobinhoodOrderLookup,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._lookup = lookup
        self._clock = clock

    def reconcile(
        self,
        request: PlacementReconciliationRequest,
    ) -> PlacementReconciliationOutcome:
        result = self._lookup.lookup(
            request
        )

        checked_at = self._clock()

        if (
            checked_at.tzinfo is None
            or checked_at.utcoffset() is None
        ):
            raise ValueError(
                "reconciliation clock must return timezone-aware datetime"
            )

        if result.status is RobinhoodOrderLookupStatus.FOUND:
            return PlacementReconciliationOutcome(
                request=request,
                status=PlacementReconciliationStatus.FOUND,
                checked_at=checked_at,
                broker_order_id=result.broker_order_id,
                message=result.message,
            )

        if (
            result.status
            is RobinhoodOrderLookupStatus.NOT_FOUND
        ):
            return PlacementReconciliationOutcome(
                request=request,
                status=PlacementReconciliationStatus.NOT_FOUND,
                checked_at=checked_at,
                message=result.message,
            )

        if (
            result.status
            is RobinhoodOrderLookupStatus.UNKNOWN
        ):
            return PlacementReconciliationOutcome(
                request=request,
                status=(
                    PlacementReconciliationStatus.STILL_UNKNOWN
                ),
                checked_at=checked_at,
                message=result.message,
            )

        raise ValueError(
            f"unsupported lookup status: {result.status}"
        )