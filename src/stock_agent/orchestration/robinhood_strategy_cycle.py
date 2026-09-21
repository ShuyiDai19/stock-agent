from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.orchestration.candidate_loading import (
    EquityCandidateLoadItem,
    EquityCandidateLoadOutcome,
    load_robinhood_equity_review_candidates,
)
from stock_agent.orchestration.entry_review_batch import (
    EntryReviewBatchItem,
)
from stock_agent.orchestration.strategy_cycle import (
    EquityStrategyCycleInput,
    EquityStrategyCycleOutcome,
    run_equity_strategy_cycle,
)
from stock_agent.risk.entry_portfolio import (
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
)
from stock_agent.orchestration.portfolio_state import (
    PositionRiskStateStore,
    load_open_position_risk_snapshots,
)
from enum import StrEnum

from stock_agent.strategy.market_session import (
    RegularMarketSession,
    XnysRegularMarketSessionResolver,
)
from stock_agent.orchestration.robinhood_universe import (
    RobinhoodUniverseScreenOutcome,
    load_and_screen_robinhood_equity_universe,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)
from stock_agent.orchestration.entry_placement_cycle import (
    ApprovedEquityEntryPlacer,
    EquityEntryExecutionMode,
    EquityEntryPlacementCycleOutcome,
    execute_approved_equity_entries,
)
from stock_agent.orchestration.entry_activation_reconciliation import (
    EquityEntryActivationReconciler,
)
from stock_agent.brokers.robinhood.entry_placement_recovery import (
    EquityEntryPlacementRecoveryService,
)


@dataclass(frozen=True, slots=True)
class RobinhoodEquityStrategyCycleOutcome:
    candidate_loading: EquityCandidateLoadOutcome
    strategy: EquityStrategyCycleOutcome

    @property
    def eligible_entries(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return (
            self.strategy
            .eligible_entries
        )

    @property
    def market_data_errors(
        self,
    ) -> tuple[
        EquityCandidateLoadItem,
        ...,
    ]:
        return (
            self.candidate_loading
            .errors
        )

    @property
    def review_errors(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return (
            self.strategy
            .errors
        )

    @property
    def loaded_candidate_count(
        self,
    ) -> int:
        return (
            self.candidate_loading
            .candidate_count
        )

    @property
    def eligible_entry_count(
        self,
    ) -> int:
        return len(
            self.eligible_entries
        )

    @property
    def market_data_error_count(
        self,
    ) -> int:
        return len(
            self.market_data_errors
        )

    @property
    def review_error_count(
        self,
    ) -> int:
        return len(
            self.review_errors
        )

class RobinhoodEquityCycleRunStatus(
    StrEnum
):
    RAN = "ran"
    NO_TRADE = "no_trade"


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodEquityCycleRunOutcome:
    status: (
        RobinhoodEquityCycleRunStatus
    )

    session: RegularMarketSession

    cycle: (
        RobinhoodEquityStrategyCycleOutcome
        | None
    )

    universe: (
        RobinhoodUniverseScreenOutcome
        | None
    ) = None

    execution: (
        EquityEntryPlacementCycleOutcome
        | None
    ) = None

    reason: str | None = None

    def __post_init__(
        self,
    ) -> None:
        if (
            self.status
            is RobinhoodEquityCycleRunStatus
            .RAN
        ):
            if self.cycle is None:
                raise ValueError(
                    "RAN outcome requires cycle"
                )

            if self.execution is None:
                raise ValueError(
                    "RAN outcome requires execution"
                )

            return

        if self.cycle is not None:
            raise ValueError(
                "NO_TRADE outcome cannot "
                "contain cycle"
            )

        if self.execution is not None:
            raise ValueError(
                "NO_TRADE outcome cannot "
                "contain execution"
            )
    
    @property
    def eligible_entries(
        self,
    ):
        if self.cycle is None:
            return ()

        return (
            self.cycle
            .eligible_entries
        )

    @property
    def eligible_entry_count(
        self,
    ) -> int:
        return len(
            self.eligible_entries
        )

    @property
    def loaded_candidate_count(
        self,
    ) -> int:
        if self.cycle is None:
            return 0

        return (
            self.cycle
            .loaded_candidate_count
        )

    @property
    def market_data_error_count(
        self,
    ) -> int:
        if self.cycle is None:
            return 0

        return (
            self.cycle
            .market_data_error_count
        )

    @property
    def review_error_count(
        self,
    ) -> int:
        if self.cycle is None:
            return 0

        return (
            self.cycle
            .review_error_count
        )

    @property
    def universe_eligible_symbols(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        if self.universe is None:
            return ()

        return (
            self.universe
            .eligible_symbols
        )


    @property
    def universe_selected_symbols(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        if self.universe is None:
            return ()

        return (
            self.universe
            .selected_symbols
        )


    @property
    def universe_error_count(
        self,
    ) -> int:
        if self.universe is None:
            return 0

        return len(
            self.universe
            .load_errors
        )


    @property
    def universe_rejected_count(
        self,
    ) -> int:
        if self.universe is None:
            return 0

        return len(
            self.universe
            .rejected_items
        )


    @property
    def universe_deferred_count(
        self,
    ) -> int:
        if self.universe is None:
            return 0

        return len(
            self.universe
            .deferred_items
        )

    @property
    def execution_mode(
        self,
    ) -> EquityEntryExecutionMode | None:
        if self.execution is None:
            return None

        return self.execution.mode


    @property
    def placement_count(
        self,
    ) -> int:
        if self.execution is None:
            return 0

        return self.execution.placed_count


    @property
    def placement_failure_count(
        self,
    ) -> int:
        if self.execution is None:
            return 0

        return self.execution.failed_count


    @property
    def placement_blocked_count(
        self,
    ) -> int:
        if self.execution is None:
            return 0

        return self.execution.blocked_count


def run_robinhood_equity_strategy_cycle(
    invoker: MCPToolInvoker,
    *,
    account_number: str,
    symbols: tuple[
        str,
        ...,
    ],
    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...,
    ],
    session_start: datetime,
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> RobinhoodEquityStrategyCycleOutcome:
    candidate_loading = (
        load_robinhood_equity_review_candidates(
            invoker,
            symbols=symbols,
            session_start=session_start,
            evaluated_at=evaluated_at,
            budget=budget,
        )
    )

    cycle_input = (
        EquityStrategyCycleInput(
            account_number=(
                account_number
            ),
            candidates=(
                candidate_loading
                .candidates
            ),
            open_positions=(
                open_positions
            ),
            evaluated_at=(
                evaluated_at
            ),
        )
    )

    strategy = (
        run_equity_strategy_cycle(
            invoker,
            cycle_input,
        )
    )

    return (
        RobinhoodEquityStrategyCycleOutcome(
            candidate_loading=(
                candidate_loading
            ),
            strategy=strategy,
        )
    )

def run_robinhood_equity_strategy_cycle_from_store(
    invoker: MCPToolInvoker,
    store: PositionRiskStateStore,
    *,
    account_number: str,
    allowed_symbols: tuple[
        str,
        ...,
    ],
    universe_policy: (
        EquityUniverseScreeningPolicy
    ),
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
    execution_mode: (
        EquityEntryExecutionMode
    ) = (
        EquityEntryExecutionMode
        .REVIEW_ONLY
    ),
    placer: (
        ApprovedEquityEntryPlacer
        | None
    ) = None,
    entry_recovery_service: (
        EquityEntryPlacementRecoveryService
        | None
    ) = None,
    activation_reconciler: (
        EquityEntryActivationReconciler
        | None
    ) = None,
) -> RobinhoodEquityCycleRunOutcome:
    resolver = (
        XnysRegularMarketSessionResolver()
    )

    session = resolver.resolve(
        evaluated_at
    )

    if not session.is_open:
        return (
            RobinhoodEquityCycleRunOutcome(
                status=(
                    RobinhoodEquityCycleRunStatus
                    .NO_TRADE
                ),
                session=session,
                cycle=None,
                universe=None,
                reason=(
                    "regular market session "
                    f"is {session.status.value}"
                ),
            )
        )
    
    if (
        execution_mode
        is EquityEntryExecutionMode.LIVE
    ):
        if entry_recovery_service is None:
            raise ValueError(
                "live entry execution requires "
                "entry recovery service"
            )

        if activation_reconciler is None:
            raise ValueError(
                "live entry execution requires "
                "activation reconciler"
            )

        recovery_results = (
            entry_recovery_service.recover(
                account_number=account_number
            )
        )

        if any(
            not result.recovered
            for result in recovery_results
        ):
            raise RuntimeError(
                "live entry execution blocked by "
                "unresolved entry placement recovery"
            )

        activation_reconciler.reconcile(
            account_number=account_number
        )

    universe = (
        load_and_screen_robinhood_equity_universe(
            invoker,
            symbols=allowed_symbols,
            policy=universe_policy,
        )
    )

    if not universe.selected_symbols:
        return (
            RobinhoodEquityCycleRunOutcome(
                status=(
                    RobinhoodEquityCycleRunStatus
                    .NO_TRADE
                ),
                session=session,
                cycle=None,
                universe=universe,
                reason=(
                    "universe screening produced "
                    "no eligible symbols"
                ),
            )
        )

    open_positions = (
        load_open_position_risk_snapshots(
            store,
            account_number=(
                account_number
            ),
        )
    )

    cycle = (
        run_robinhood_equity_strategy_cycle(
            invoker,
            account_number=(
                account_number
            ),
            symbols=(
                universe
                .selected_symbols
            ),
            open_positions=(
                open_positions
            ),
            session_start=(
                session.opens_at
            ),
            evaluated_at=(
                evaluated_at
            ),
            budget=budget,
        )
    )

    execution = (
        execute_approved_equity_entries(
            cycle.strategy.review_batch.items,
            mode=execution_mode,
            account_number=(
                account_number
            ),
            attempted_at=(
                evaluated_at
            ),
            placer=placer,
        )
    )

    return (
        RobinhoodEquityCycleRunOutcome(
            status=(
                RobinhoodEquityCycleRunStatus
                .RAN
            ),
            session=session,
            cycle=cycle,
            universe=universe,
            execution=execution,
        )
    )