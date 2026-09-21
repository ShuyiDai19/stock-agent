from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from stock_agent.domain import AssetType

from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationOutcome,
    PlacementReconciliationRequest,
    PlacementReconciliationStatus,
)

@dataclass(frozen=True)
class RobinhoodOrderLookupRequest:
    account_number: str
    asset_type: AssetType
    symbol: str
    ref_id: str
    option_id: str | None = None

    def __post_init__(self) -> None:
        if not self.account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if not self.ref_id.strip():
            raise ValueError(
                "ref_id cannot be empty"
            )

        if (
            self.asset_type
            is AssetType.EQUITY
            and self.option_id is not None
        ):
            raise ValueError(
                "equity lookup cannot "
                "contain option_id"
            )

        if (
            self.asset_type
            is AssetType.OPTION
        ):
            if (
                self.option_id is None
                or not self.option_id.strip()
            ):
                raise ValueError(
                    "option lookup requires "
                    "option_id"
                )

class RobinhoodOrderLookupStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"

def build_robinhood_order_lookup_request(
    request: PlacementReconciliationRequest,
) -> RobinhoodOrderLookupRequest:
    return RobinhoodOrderLookupRequest(
        account_number=(
            request.account_number
        ),
        asset_type=request.asset_type,
        symbol=request.symbol,
        ref_id=request.ref_id,
        option_id=request.option_id,
    )

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
        request: RobinhoodOrderLookupRequest,
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
        not_found_grace_period: timedelta,
    ) -> None:
        if not_found_grace_period < timedelta(0):
            raise ValueError(
                "not_found_grace_period cannot be negative"
            )

        self._lookup = lookup
        self._clock = clock
        self._not_found_grace_period = (
            not_found_grace_period
        )

    def reconcile(
        self,
        request: PlacementReconciliationRequest,
    ) -> PlacementReconciliationOutcome:
        lookup_request = (
            build_robinhood_order_lookup_request(
                request
            )
        )

        result = self._lookup.lookup(
            lookup_request
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
            elapsed = (
                checked_at
                - request.placement_attempted_at
            )

            if elapsed < timedelta(0):
                raise ValueError(
                    "reconciliation check cannot precede "
                    "placement attempt"
                )

            if elapsed < self._not_found_grace_period:
                return PlacementReconciliationOutcome(
                    request=request,
                    status=(
                        PlacementReconciliationStatus.STILL_UNKNOWN
                    ),
                    checked_at=checked_at,
                    message=(
                        "order not found within placement "
                        "reconciliation grace period"
                    ),
                )

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