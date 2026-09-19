from dataclasses import dataclass

from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptRecord,
    PlacementAttemptStatus,
)
from stock_agent.domain import AssetType


class ClosingOrderProvenanceError(
    RuntimeError
):
    pass


@dataclass(frozen=True, slots=True)
class ClosingOrderProvenance:
    position_id: str
    account_number: str
    asset_type: AssetType
    symbol: str
    ref_id: str
    broker_order_id: str
    option_id: str | None = None

    def __post_init__(
        self,
    ) -> None:
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

        if not self.broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )


def build_closing_order_provenance(
    record: PlacementAttemptRecord,
) -> ClosingOrderProvenance | None:
    broker_order_id: str | None = None

    if (
        record.status
        is PlacementAttemptStatus.ACKNOWLEDGED
    ):
        acknowledgement = record.acknowledgement

        if acknowledgement is None:
            raise ClosingOrderProvenanceError(
                "acknowledged placement is missing "
                "acknowledgement evidence"
            )

        broker_order_id = (
            acknowledgement.broker_order_id
        )

    elif (
        record.status
        is PlacementAttemptStatus.RECOVERED
    ):
        recovery_evidence = (
            record.recovery_evidence
        )

        if recovery_evidence is None:
            raise ClosingOrderProvenanceError(
                "recovered placement is missing "
                "recovery evidence"
            )

        broker_order_id = (
            recovery_evidence.broker_order_id
        )

    else:
        return None

    request = record.submission.request

    return ClosingOrderProvenance(
        position_id=request.position_id,
        account_number=request.account_number,
        asset_type=request.asset_type,
        symbol=request.symbol,
        ref_id=record.submission.ref_id,
        broker_order_id=broker_order_id,
        option_id=request.option_id,
    )


def resolve_closing_order_provenance(
    records: list[PlacementAttemptRecord],
    *,
    position_id: str,
) -> ClosingOrderProvenance | None:
    if not position_id.strip():
        raise ValueError(
            "position_id cannot be empty"
        )

    matches: list[
        ClosingOrderProvenance
    ] = []

    for record in records:
        provenance = (
            build_closing_order_provenance(
                record
            )
        )

        if provenance is None:
            continue

        if (
            provenance.position_id
            != position_id
        ):
            continue

        matches.append(
            provenance
        )

    if not matches:
        return None

    if len(matches) > 1:
        raise ClosingOrderProvenanceError(
            "multiple resolved closing orders "
            "exist for position"
        )

    return matches[0]