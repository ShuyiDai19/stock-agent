from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from stock_agent.monitoring import (
    PositionMonitorOutcome,
)


class EquityExitReconciler(Protocol):
    def reconcile(
        self,
        *,
        account_number: str,
    ):
        ...


class EquityPositionMonitor(Protocol):
    def monitor_active_positions(
        self,
        *,
        account_number: str,
    ) -> list[PositionMonitorOutcome]:
        ...


class EquityExitExecutionCoordinator(
    Protocol
):
    def execute_outcome(
        self,
        outcome: PositionMonitorOutcome,
    ) -> ExecutionResult | None:
        ...


class RobinhoodEquityExitCycleStatus(
    str,
    Enum,
):
    NO_ACTION = "no_action"
    PREVIEWED = "previewed"
    SUBMITTED = "submitted"


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodEquityExitCycleResult:
    status: RobinhoodEquityExitCycleStatus
    monitored_position_count: int
    actionable_exit_count: int
    execution_result: (
        ExecutionResult | None
    ) = None

    @property
    def order_submitted(
        self,
    ) -> bool:
        return (
            self.status
            is RobinhoodEquityExitCycleStatus
            .SUBMITTED
        )


class RobinhoodEquityExitCycleError(
    RuntimeError
):
    pass


def run_robinhood_equity_exit_cycle(
    *,
    account_number: str,
    reconciler: EquityExitReconciler,
    monitor: EquityPositionMonitor,
    execution_coordinator: (
        EquityExitExecutionCoordinator
    ),
) -> RobinhoodEquityExitCycleResult:
    if not account_number.strip():
        raise ValueError(
            "account_number cannot be empty"
        )

    # Existing exits always settle first.
    #
    # The reconciler itself fails closed if a
    # CLOSING equity position remains unresolved.
    reconciler.reconcile(
        account_number=account_number
    )

    outcomes = (
        monitor.monitor_active_positions(
            account_number=account_number
        )
    )

    failed_outcomes = [
        outcome
        for outcome in outcomes
        if not outcome.succeeded
    ]

    if failed_outcomes:
        raise RobinhoodEquityExitCycleError(
            "equity exit monitoring failed "
            "for one or more active positions"
        )

    actionable = [
        outcome
        for outcome in outcomes
        if outcome.exit_intent is not None
    ]

    # Never choose arbitrarily between multiple
    # simultaneous equity exits.
    #
    # This preserves the invariant:
    #
    #   one cycle <= one equity order
    #
    if len(actionable) > 1:
        raise RobinhoodEquityExitCycleError(
            "multiple equity exit intents "
            "were produced in one cycle"
        )

    if not actionable:
        return (
            RobinhoodEquityExitCycleResult(
                status=(
                    RobinhoodEquityExitCycleStatus
                    .NO_ACTION
                ),
                monitored_position_count=(
                    len(outcomes)
                ),
                actionable_exit_count=0,
                execution_result=None,
            )
        )

    result = (
        execution_coordinator.execute_outcome(
            actionable[0]
        )
    )

    if result is None:
        raise RobinhoodEquityExitCycleError(
            "actionable equity exit produced "
            "no execution result"
        )

    if (
        result.status
        is ExecutionStatus.SUBMITTED
    ):
        status = (
            RobinhoodEquityExitCycleStatus
            .SUBMITTED
        )
    elif (
        result.status
        is ExecutionStatus.PREVIEWED
    ):
        status = (
            RobinhoodEquityExitCycleStatus
            .PREVIEWED
        )
    else:
        raise RobinhoodEquityExitCycleError(
            "equity exit execution returned "
            f"unexpected status: "
            f"{result.status.value!r}"
        )

    return RobinhoodEquityExitCycleResult(
        status=status,
        monitored_position_count=(
            len(outcomes)
        ),
        actionable_exit_count=1,
        execution_result=result,
    )