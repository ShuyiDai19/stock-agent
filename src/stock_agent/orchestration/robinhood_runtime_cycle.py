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


def run_robinhood_equity_cycle_from_runtime(
    runtime: RobinhoodRuntimeSession,
    *,
    allowed_symbols: tuple[str, ...],
    universe_policy: EquityUniverseScreeningPolicy,
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> RobinhoodEquityCycleRunOutcome:
    if runtime.live_execution_enabled:
        if runtime.entry_placer is None:
            raise RuntimeError(
                "live runtime is missing "
                "entry placer"
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

    return (
        run_robinhood_equity_strategy_cycle_from_store(
            runtime._strategy_invoker,
            runtime.position_store,
            account_number=(
                runtime.account_number
            ),
            allowed_symbols=allowed_symbols,
            universe_policy=universe_policy,
            evaluated_at=evaluated_at,
            budget=budget,
            execution_mode=execution_mode,
            placer=placer,
            entry_recovery_service=(
                entry_recovery_service
            ),
            activation_reconciler=(
                activation_reconciler
            ),
            preflight_reader=(
                preflight_reader
            ),
            preflight_opening_debit=(
                preflight_opening_debit
            ),
        )
    )