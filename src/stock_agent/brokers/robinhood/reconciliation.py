from dataclasses import dataclass

from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)
from stock_agent.domain import AssetType
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class PlacementReconciliationRequest:
    position_id: str
    account_number: str
    asset_type: AssetType
    symbol: str
    ref_id: str
    placement_attempted_at: datetime
    option_id: str | None = None

    def __post_init__(self) -> None:
        if not self.position_id.strip():
            raise ValueError(
                "position_id cannot be empty"
            )

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
            self.asset_type is AssetType.EQUITY
            and self.option_id is not None
        ):
            raise ValueError(
                "equity reconciliation cannot contain option_id"
            )

        if self.asset_type is AssetType.OPTION:
            if (
                self.option_id is None
                or not self.option_id.strip()
            ):
                raise ValueError(
                    "option reconciliation requires option_id"
                )

class PlacementReconciliationStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    STILL_UNKNOWN = "still_unknown"


@dataclass(frozen=True)
class PlacementReconciliationOutcome:
    request: PlacementReconciliationRequest
    status: PlacementReconciliationStatus
    checked_at: datetime
    broker_order_id: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if (
            self.checked_at.tzinfo is None
            or self.checked_at.utcoffset() is None
        ):
            raise ValueError(
                "checked_at must be timezone-aware"
            )

        if self.status is PlacementReconciliationStatus.FOUND:
            if (
                self.broker_order_id is None
                or not self.broker_order_id.strip()
            ):
                raise ValueError(
                    "found reconciliation requires broker_order_id"
                )
        elif self.broker_order_id is not None:
            raise ValueError(
                "non-found reconciliation cannot contain broker_order_id"
            )

        if (
            self.message is not None
            and not self.message.strip()
        ):
            raise ValueError(
                "message cannot be empty"
            )


def build_placement_reconciliation_request(
    submission: RobinhoodExitSubmission,
    *,
    placement_attempted_at: datetime,
) -> PlacementReconciliationRequest:
    request = submission.request

    return PlacementReconciliationRequest(
        position_id=request.position_id,
        account_number=request.account_number,
        asset_type=request.asset_type,
        symbol=request.symbol,
        ref_id=submission.ref_id,
        placement_attempted_at=placement_attempted_at,
        option_id=request.option_id,
    )