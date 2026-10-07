from decimal import Decimal
from typing import Protocol

from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightBlocker,
    EquityEntryPreflightDataUnavailableError,
    EquityEntryPreflightResult,
    EquityEntryPreflightSnapshot,
    evaluate_equity_entry_preflight,
)


class EquityEntryPreflightSnapshotReader(
    Protocol
):
    def read(
        self,
        *,
        account_number: str,
        evaluated_at,
    ) -> EquityEntryPreflightSnapshot:
        ...


class EquityEntryPreflightBlockedError(
    RuntimeError
):
    def __init__(
        self,
        result: EquityEntryPreflightResult,
    ) -> None:
        if result.eligible:
            raise ValueError(
                "blocked error requires "
                "ineligible preflight result"
            )

        self.result = result

        blocker_names = ",".join(
            blocker.value
            for blocker in result.blockers
        )

        super().__init__(
            "live entry execution blocked "
            "by preflight: "
            f"{blocker_names}"
        )


def require_live_equity_entry_preflight(
    reader: EquityEntryPreflightSnapshotReader,
    *,
    account_number: str,
    evaluated_at,
    opening_debit: Decimal,
    minimum_cash_reserve: Decimal = (
        Decimal("5")
    ),
) -> EquityEntryPreflightResult:
    try:
        snapshot = reader.read(
            account_number=account_number,
            evaluated_at=evaluated_at,
        )

    except EquityEntryPreflightDataUnavailableError as exc:
        unavailable = (
            EquityEntryPreflightResult(
                blockers=(
                    EquityEntryPreflightBlocker
                    .DATA_UNAVAILABLE,
                ),
                unavailable_sources=(
                    exc.source,
                ),
            )
        )

        raise (
            EquityEntryPreflightBlockedError(
                unavailable
            )
        ) from exc

    except Exception as exc:
        # Unknown reader failure still fails closed.
        unavailable = (
            EquityEntryPreflightResult(
                blockers=(
                    EquityEntryPreflightBlocker
                    .DATA_UNAVAILABLE,
                ),
            )
        )

        raise (
            EquityEntryPreflightBlockedError(
                unavailable
            )
        ) from exc

    result = (
        evaluate_equity_entry_preflight(
            snapshot,
            evaluated_at=evaluated_at,
            opening_debit=opening_debit,
            minimum_cash_reserve=(
                minimum_cash_reserve
            ),
        )
    )

    if not result.eligible:
        raise (
            EquityEntryPreflightBlockedError(
                result
            )
        )

    return result