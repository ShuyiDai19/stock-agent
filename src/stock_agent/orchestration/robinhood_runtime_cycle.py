from datetime import datetime
from decimal import Decimal

from stock_agent.brokers.robinhood.broker_runtime import (
    RobinhoodRuntimeSession,
)
from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
)
from stock_agent.orchestration.robinhood_strategy_cycle import (
    DEFAULT_ENTRY_BUDGET,
    RobinhoodEquityCycleRunOutcome,
    run_robinhood_equity_strategy_cycle_from_store,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)
from dataclasses import dataclass
from typing import Any, Callable

from stock_agent.brokers.robinhood.exit_executor import (
    DryRunRobinhoodExitExecutor,
    LiveRobinhoodExitExecutor,
)
from stock_agent.execution import (
    ExitExecutionService,
)
from stock_agent.monitoring.trailing_stop_monitor import (
    TrailingStopMonitor,
)
from stock_agent.orchestration.exit_execution import (
    ExitExecutionCoordinator,
)
from stock_agent.orchestration.robinhood_equity_exit_cycle import (
    RobinhoodEquityExitCycleResult,
    RobinhoodEquityExitCycleStatus,
    run_robinhood_equity_exit_cycle,
)
from stock_agent.domain import AssetType

@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodEquityRuntimeCycleResult:
    exit_result: (
        RobinhoodEquityExitCycleResult
    )
    entry_result: Any | None

    def __post_init__(
        self,
    ) -> None:
        exit_actionable = (
            self.exit_result.status
            is not RobinhoodEquityExitCycleStatus
            .NO_ACTION
        )

        if (
            exit_actionable
            and self.entry_result is not None
        ):
            raise ValueError(
                "entry cycle cannot run after "
                "an actionable equity exit"
            )

        if (
            not exit_actionable
            and self.entry_result is None
        ):
            raise ValueError(
                "entry result is required when "
                "exit cycle has no action"
            )

    @property
    def exit_order_submitted(
        self,
    ) -> bool:
        return (
            self.exit_result.status
            is RobinhoodEquityExitCycleStatus
            .SUBMITTED
        )

    @property
    def exit_previewed(
        self,
    ) -> bool:
        return (
            self.exit_result.status
            is RobinhoodEquityExitCycleStatus
            .PREVIEWED
        )

    @property
    def entry_order_submitted(
        self,
    ) -> bool:
        if self.entry_result is None:
            return False

        return (
            self.entry_result
            .placement_count
            > 0
        )

    @property
    def placement_count(
        self,
    ) -> int:
        if self.entry_result is None:
            return 0

        return (
            self.entry_result
            .placement_count
        )

    @property
    def placement_failure_count(
        self,
    ) -> int:
        if self.entry_result is None:
            return 0

        return (
            self.entry_result
            .placement_failure_count
        )


def run_robinhood_equity_cycle_from_runtime(
    runtime: RobinhoodRuntimeSession,
    *,
    allowed_symbols: tuple[str, ...],
    universe_policy: EquityUniverseScreeningPolicy,
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
    exit_cycle_runner=None,
    entry_cycle_runner=None,
    candidate_loader=None,
    execution_clock: (
        Callable[[], datetime]
        | None
    ) = None,
) -> RobinhoodEquityRuntimeCycleResult:
    if exit_cycle_runner is None:
        exit_cycle_runner = (
            run_robinhood_equity_exit_cycle_from_runtime
        )

    if entry_cycle_runner is None:
        entry_cycle_runner = (
            run_robinhood_equity_strategy_cycle_from_store
        )

    exit_result = exit_cycle_runner(
        runtime,
        evaluated_at=evaluated_at,
    )

    if (
        exit_result.status
        is not RobinhoodEquityExitCycleStatus
        .NO_ACTION
    ):
        return (
            RobinhoodEquityRuntimeCycleResult(
                exit_result=exit_result,
                entry_result=None,
            )
        )

    if runtime.live_execution_enabled:
        if runtime.entry_placer is None:
            raise RuntimeError(
                "live runtime is missing "
                "entry placer"
            )

        if runtime.entry_recovery_service is None:
            raise RuntimeError(
                "live runtime is missing "
                "entry recovery service"
            )

        if (
            runtime.entry_activation_reconciler
            is None
        ):
            raise RuntimeError(
                "live runtime is missing "
                "entry activation reconciler"
            )

        if runtime.entry_preflight_reader is None:
            raise RuntimeError(
                "live runtime is missing "
                "entry preflight reader"
            )

        execution_mode = (
            EquityEntryExecutionMode.LIVE
        )

        placer = runtime.entry_placer

        entry_recovery_service = (
            runtime.entry_recovery_service
        )

        activation_reconciler = (
            runtime.entry_activation_reconciler
        )

        preflight_reader = (
            runtime.entry_preflight_reader
        )

        preflight_opening_debit = (
            budget
        )

    else:
        execution_mode = (
            EquityEntryExecutionMode
            .REVIEW_ONLY
        )

        placer = None
        entry_recovery_service = None
        activation_reconciler = None
        preflight_reader = None
        preflight_opening_debit = None

    entry_cycle_kwargs = {
        "account_number": (
            runtime.account_number
        ),
        "allowed_symbols": (
            allowed_symbols
        ),
        "universe_policy": (
            universe_policy
        ),
        "evaluated_at": (
            evaluated_at
        ),
        "budget": (
            budget
        ),
        "execution_mode": (
            execution_mode
        ),
        "placer": (
            placer
        ),
        "entry_recovery_service": (
            entry_recovery_service
        ),
        "activation_reconciler": (
            activation_reconciler
        ),
        "preflight_reader": (
            preflight_reader
        ),
        "preflight_opening_debit": (
            preflight_opening_debit
        ),
    }

    if candidate_loader is not None:
        entry_cycle_kwargs[
            "candidate_loader"
        ] = candidate_loader

    if execution_clock is not None:
        entry_cycle_kwargs[
            "execution_clock"
        ] = execution_clock

    entry_result = (
        entry_cycle_runner(
            runtime._strategy_invoker,
            runtime.position_store,
            **entry_cycle_kwargs,
        )
    )

    return (
        RobinhoodEquityRuntimeCycleResult(
            exit_result=exit_result,
            entry_result=entry_result,
        )
    )

def run_robinhood_equity_exit_cycle_from_runtime(
    runtime,
    *,
    evaluated_at,
) -> RobinhoodEquityExitCycleResult:
    monitor = TrailingStopMonitor(
        runtime.position_store,
        runtime.equity_quote_provider,
        asset_type_filter=(
            AssetType.EQUITY
        ),
    )

    if runtime.live_execution_enabled:
        executor = (
            LiveRobinhoodExitExecutor(
                runtime.broker,
                runtime
                .equity_exit_price_provider,
            )
        )
    else:
        executor = (
            DryRunRobinhoodExitExecutor(
                clock=lambda: evaluated_at,
            )
        )

    execution_service = (
        ExitExecutionService(
            executor
        )
    )

    execution_coordinator = (
        ExitExecutionCoordinator(
            execution_service,
            runtime.position_store,
        )
    )

    return (
        run_robinhood_equity_exit_cycle(
            account_number=(
                runtime.account_number
            ),
            reconciler=(
                runtime
                .equity_exit_reconciler
            ),
            monitor=monitor,
            execution_coordinator=(
                execution_coordinator
            ),
        )
    )