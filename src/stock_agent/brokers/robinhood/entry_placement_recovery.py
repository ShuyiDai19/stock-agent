from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from stock_agent.brokers.robinhood.entry_placement import (
    EquityEntryPlacementRecord,
)
from stock_agent.brokers.robinhood.reconciler import (
    RobinhoodOrderLookup,
    RobinhoodOrderLookupRequest,
    RobinhoodOrderLookupResult,
    RobinhoodOrderLookupStatus,
)
from stock_agent.domain import AssetType


class EquityEntryRecoveryJournal(Protocol):
    def list_uncertain(
        self,
        *,
        account_number: str,
    ) -> list[EquityEntryPlacementRecord]:
        ...

    def recover_acknowledged(
        self,
        ref_id: str,
        *,
        broker_order_id: str,
        recovered_at: datetime,
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class EquityEntryPlacementRecoveryResult:
    record: EquityEntryPlacementRecord
    lookup_result: RobinhoodOrderLookupResult | None = None
    checked_at: datetime | None = None
    error: Exception | None = None
    persistence_error: Exception | None = None

    def __post_init__(self) -> None:
        if self.error is not None:
            if (
                self.lookup_result is not None
                or self.checked_at is not None
                or self.persistence_error is not None
            ):
                raise ValueError(
                    "lookup error cannot coexist with "
                    "lookup result, checked_at, or "
                    "persistence error"
                )

            return

        if self.lookup_result is None:
            raise ValueError(
                "recovery result requires "
                "lookup_result or error"
            )

        if self.checked_at is None:
            raise ValueError(
                "successful lookup requires checked_at"
            )

        if (
            self.checked_at.tzinfo is None
            or self.checked_at.utcoffset() is None
        ):
            raise ValueError(
                "checked_at must be timezone-aware"
            )

        if (
            self.persistence_error is not None
            and self.lookup_result.status
            is not RobinhoodOrderLookupStatus.FOUND
        ):
            raise ValueError(
                "persistence error requires "
                "found lookup result"
            )

    @property
    def recovered(self) -> bool:
        return (
            self.error is None
            and self.persistence_error is None
            and self.lookup_result is not None
            and self.lookup_result.status
            is RobinhoodOrderLookupStatus.FOUND
        )


class EquityEntryPlacementRecoveryService:
    def __init__(
        self,
        journal: EquityEntryRecoveryJournal,
        lookup: RobinhoodOrderLookup,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._journal = journal
        self._lookup = lookup
        self._clock = clock

    def recover(
        self,
        *,
        account_number: str,
    ) -> list[EquityEntryPlacementRecoveryResult]:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        results: list[
            EquityEntryPlacementRecoveryResult
        ] = []

        for record in self._journal.list_uncertain(
            account_number=account_number
        ):
            request = RobinhoodOrderLookupRequest(
                account_number=record.account_number,
                asset_type=AssetType.EQUITY,
                symbol=record.symbol,
                ref_id=record.ref_id,
                option_id=None,
            )

            try:
                lookup_result = self._lookup.lookup(
                    request
                )
            except Exception as exc:
                results.append(
                    EquityEntryPlacementRecoveryResult(
                        record=record,
                        error=exc,
                    )
                )
                continue

            checked_at = self._clock()

            if (
                checked_at.tzinfo is None
                or checked_at.utcoffset()
                is None
            ):
                raise ValueError(
                    "recovery clock must return "
                    "timezone-aware datetime"
                )

            if (
                lookup_result.status
                is RobinhoodOrderLookupStatus.FOUND
            ):
                try:
                    self._journal.recover_acknowledged(
                        record.ref_id,
                        broker_order_id=(
                            lookup_result
                            .broker_order_id
                        ),
                        recovered_at=checked_at,
                    )
                except Exception as exc:
                    results.append(
                        EquityEntryPlacementRecoveryResult(
                            record=record,
                            lookup_result=(
                                lookup_result
                            ),
                            checked_at=checked_at,
                            persistence_error=exc,
                        )
                    )
                    continue

            results.append(
                EquityEntryPlacementRecoveryResult(
                    record=record,
                    lookup_result=lookup_result,
                    checked_at=checked_at,
                )
            )

        return results