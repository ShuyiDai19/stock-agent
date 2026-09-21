from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from stock_agent.orchestration.entry_review_batch import (
    EntryReviewBatchItem,
)


class EquityEntryExecutionMode(
    StrEnum
):
    REVIEW_ONLY = "review_only"
    LIVE = "live"


class EquityEntryPlacementStatus(
    StrEnum
):
    REVIEW_ONLY = "review_only"
    PLACED = "placed"
    FAILED = "failed"
    BLOCKED = "blocked"


class EquityEntryPlacementReceipt(
    Protocol
):
    ref_id: str
    broker_order_id: str
    submitted_at: datetime


class ApprovedEquityEntryPlacer(
    Protocol
):
    def place(
        self,
        item: EntryReviewBatchItem,
        *,
        account_number: str,
        attempted_at: datetime,
    ) -> EquityEntryPlacementReceipt:
        ...


@dataclass(frozen=True, slots=True)
class EquityEntryPlacementCycleItem:
    symbol: str
    status: EquityEntryPlacementStatus

    placement: (
        EquityEntryPlacementReceipt
        | None
    ) = None

    error: Exception | None = None

    blocked_by_symbol: (
        str | None
    ) = None

    def __post_init__(
        self,
    ) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        if (
            self.status
            is EquityEntryPlacementStatus
            .REVIEW_ONLY
        ):
            if (
                self.placement is not None
                or self.error is not None
                or self.blocked_by_symbol
                is not None
            ):
                raise ValueError(
                    "review-only item cannot "
                    "contain placement, error, "
                    "or blocker"
                )

            return

        if (
            self.status
            is EquityEntryPlacementStatus
            .PLACED
        ):
            if (
                self.placement is None
                or self.error is not None
                or self.blocked_by_symbol
                is not None
            ):
                raise ValueError(
                    "placed item requires "
                    "placement only"
                )

            return

        if (
            self.status
            is EquityEntryPlacementStatus
            .FAILED
        ):
            if (
                self.placement is not None
                or self.error is None
                or self.blocked_by_symbol
                is not None
            ):
                raise ValueError(
                    "failed item requires "
                    "error only"
                )

            return

        if (
            self.status
            is EquityEntryPlacementStatus
            .BLOCKED
        ):
            if (
                self.placement is not None
                or self.error is not None
                or self.blocked_by_symbol
                is None
                or not self.blocked_by_symbol
                .strip()
            ):
                raise ValueError(
                    "blocked item requires "
                    "blocking symbol only"
                )

            return

        raise ValueError(
            "unsupported placement status"
        )


@dataclass(frozen=True, slots=True)
class EquityEntryPlacementCycleOutcome:
    mode: EquityEntryExecutionMode

    items: tuple[
        EquityEntryPlacementCycleItem,
        ...,
    ]

    @property
    def placed_items(
        self,
    ) -> tuple[
        EquityEntryPlacementCycleItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if (
                item.status
                is EquityEntryPlacementStatus
                .PLACED
            )
        )

    @property
    def failed_items(
        self,
    ) -> tuple[
        EquityEntryPlacementCycleItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if (
                item.status
                is EquityEntryPlacementStatus
                .FAILED
            )
        )

    @property
    def placed_count(
        self,
    ) -> int:
        return len(
            self.placed_items
        )

    @property
    def failed_count(
        self,
    ) -> int:
        return len(
            self.failed_items
        )

    @property
    def blocked_items(
        self,
    ) -> tuple[
        EquityEntryPlacementCycleItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if (
                item.status
                is EquityEntryPlacementStatus
                .BLOCKED
            )
        )


    @property
    def blocked_count(
        self,
    ) -> int:
        return len(
            self.blocked_items
        )


def execute_approved_equity_entries(
    items: tuple[
        EntryReviewBatchItem,
        ...,
    ],
    *,
    mode: EquityEntryExecutionMode,
    account_number: str,
    attempted_at: datetime,
    placer: (
        ApprovedEquityEntryPlacer
        | None
    ) = None,
) -> EquityEntryPlacementCycleOutcome:
    if not account_number.strip():
        raise ValueError(
            "account_number cannot be empty"
        )

    if (
        attempted_at.tzinfo is None
        or attempted_at.utcoffset()
        is None
    ):
        raise ValueError(
            "attempted_at must be "
            "timezone-aware"
        )

    eligible_items = tuple(
        item
        for item in items
        if item.eligible_to_place
    )

    if (
        mode
        is EquityEntryExecutionMode.LIVE
        and eligible_items
        and placer is None
    ):
        raise ValueError(
            "live entry execution "
            "requires placer"
        )

    outcomes = []

    placement_blocked_by = None

    for item in eligible_items:
        if (
            mode
            is EquityEntryExecutionMode
            .REVIEW_ONLY
        ):
            outcomes.append(
                EquityEntryPlacementCycleItem(
                    symbol=item.symbol,
                    status=(
                        EquityEntryPlacementStatus
                        .REVIEW_ONLY
                    ),
                )
            )

            continue

        if (
            placement_blocked_by
            is not None
        ):
            outcomes.append(
                EquityEntryPlacementCycleItem(
                    symbol=item.symbol,
                    status=(
                        EquityEntryPlacementStatus
                        .BLOCKED
                    ),
                    blocked_by_symbol=(
                        placement_blocked_by
                    ),
                )
            )

            continue

        assert placer is not None

        try:
            placement = placer.place(
                item,
                account_number=(
                    account_number
                ),
                attempted_at=(
                    attempted_at
                ),
            )

        except Exception as error:
            outcomes.append(
                EquityEntryPlacementCycleItem(
                    symbol=item.symbol,
                    status=(
                        EquityEntryPlacementStatus
                        .FAILED
                    ),
                    error=error,
                )
            )

            placement_blocked_by = (
                item.symbol
            )

            continue

        outcomes.append(
            EquityEntryPlacementCycleItem(
                symbol=item.symbol,
                status=(
                    EquityEntryPlacementStatus
                    .PLACED
                ),
                placement=placement,
            )
        )

    return EquityEntryPlacementCycleOutcome(
        mode=mode,
        items=tuple(
            outcomes
        ),
    )