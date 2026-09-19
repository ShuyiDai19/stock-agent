from dataclasses import dataclass
from enum import StrEnum

from stock_agent.brokers.robinhood.position_reconciliation import (
    EquityPositionReconciliationIssue,
    EquityPositionReconciliationOutcome,
)

from stock_agent.state.models import (
    PositionStateStatus,
)


class EquityPositionReconciliationAction(
    StrEnum
):
    MARK_RECONCILED = "mark_reconciled"

    SYNC_CLOSING_QUANTITY = (
        "sync_closing_quantity"
    )

    REQUIRE_RECONCILIATION = (
        "require_reconciliation"
    )

    BROKER_ONLY_REVIEW = (
        "broker_only_review"
    )


@dataclass(frozen=True, slots=True)
class EquityPositionReconciliationDecision:
    outcome: EquityPositionReconciliationOutcome
    action: EquityPositionReconciliationAction


def decide_equity_position_reconciliation(
    outcome: EquityPositionReconciliationOutcome,
) -> EquityPositionReconciliationDecision:
    local_state = outcome.local_state
    broker_position = outcome.broker_position

    if (
        local_state is None
        and broker_position is not None
    ):
        return EquityPositionReconciliationDecision(
            outcome=outcome,
            action=(
                EquityPositionReconciliationAction
                .BROKER_ONLY_REVIEW
            ),
        )

    if local_state is None:
        raise ValueError(
            "reconciliation outcome has no "
            "local position to act on"
        )

    if (
        local_state.status
        is PositionStateStatus.CLOSING
    ):
        if broker_position is None:
            return EquityPositionReconciliationDecision(
                outcome=outcome,
                action=(
                    EquityPositionReconciliationAction
                    .REQUIRE_RECONCILIATION
                ),
            )

        if (
            EquityPositionReconciliationIssue
            .UNSUPPORTED_POSITION_TYPE
            in outcome.issues
        ):
            return EquityPositionReconciliationDecision(
                outcome=outcome,
                action=(
                    EquityPositionReconciliationAction
                    .REQUIRE_RECONCILIATION
                ),
            )

        if (
            broker_position.quantity
            < local_state.remaining_quantity
            and broker_position.quantity > 0
        ):
            return EquityPositionReconciliationDecision(
                outcome=outcome,
                action=(
                    EquityPositionReconciliationAction
                    .SYNC_CLOSING_QUANTITY
                ),
            )

        if (
            broker_position.quantity
            > local_state.remaining_quantity
        ):
            return EquityPositionReconciliationDecision(
                outcome=outcome,
                action=(
                    EquityPositionReconciliationAction
                    .REQUIRE_RECONCILIATION
                ),
            )

    if not outcome.issues:
        return EquityPositionReconciliationDecision(
            outcome=outcome,
            action=(
                EquityPositionReconciliationAction
                .MARK_RECONCILED
            ),
        )

    return EquityPositionReconciliationDecision(
        outcome=outcome,
        action=(
            EquityPositionReconciliationAction
            .REQUIRE_RECONCILIATION
        ),
    )

def decide_equity_position_reconciliations(
    outcomes: tuple[
        EquityPositionReconciliationOutcome,
        ...
    ],
) -> tuple[
    EquityPositionReconciliationDecision,
    ...
]:
    return tuple(
        decide_equity_position_reconciliation(
            outcome
        )
        for outcome in outcomes
    )