from dataclasses import dataclass
from datetime import datetime

from stock_agent.brokers.robinhood.position_reader import (
    MCPRobinhoodEquityPositionReader,
)
from stock_agent.brokers.robinhood.position_reconciliation import (
    EquityPositionReconciliationOutcome,
    reconcile_equity_positions,
)
from stock_agent.brokers.robinhood.position_reconciliation_policy import (
    EquityPositionReconciliationDecision,
    decide_equity_position_reconciliations,
)
from stock_agent.brokers.robinhood.position_reconciliation_store import (
    EquityPositionReconciliationApplyResult,
    apply_equity_position_reconciliation,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
)
from stock_agent.state.models import (
    PositionStateStatus,
)
from stock_agent.state.store import (
    PositionStateStore,
)


@dataclass(frozen=True, slots=True)
class EquityPositionReconciliationRun:
    broker_positions: tuple[
        RobinhoodEquityPositionSnapshot,
        ...
    ]
    outcomes: tuple[
        EquityPositionReconciliationOutcome,
        ...
    ]
    decisions: tuple[
        EquityPositionReconciliationDecision,
        ...
    ]
    applications: tuple[
        EquityPositionReconciliationApplyResult,
        ...
    ]


class EquityPositionReconciliationService:
    def __init__(
        self,
        reader: MCPRobinhoodEquityPositionReader,
        store: PositionStateStore,
    ) -> None:
        self._reader = reader
        self._store = store

    def run(
        self,
        *,
        account_number: str,
        reconciled_at: datetime,
    ) -> EquityPositionReconciliationRun:
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if (
            reconciled_at.tzinfo is None
            or reconciled_at.utcoffset() is None
        ):
            raise ValueError(
                "reconciled_at must be "
                "timezone-aware"
            )

        broker_result = self._reader.read(
            account_number=account_number
        )

        local_states = (
            self._store.list_by_status(
                account_number=account_number,
                statuses=(
                    PositionStateStatus.ACTIVE,
                    PositionStateStatus.CLOSING,
                    PositionStateStatus
                    .RECONCILIATION_REQUIRED,
                ),
            )
        )

        outcomes = reconcile_equity_positions(
            account_number=account_number,
            local_states=local_states,
            broker_positions=(
                broker_result.positions
            ),
        )

        decisions = (
            decide_equity_position_reconciliations(
                outcomes
            )
        )

        applications = tuple(
            apply_equity_position_reconciliation(
                store=self._store,
                decision=decision,
                reconciled_at=reconciled_at,
            )
            for decision in decisions
        )

        return EquityPositionReconciliationRun(
            broker_positions=(
                broker_result.positions
            ),
            outcomes=outcomes,
            decisions=decisions,
            applications=applications,
        )