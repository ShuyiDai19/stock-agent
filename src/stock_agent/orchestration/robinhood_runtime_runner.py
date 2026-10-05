from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from stock_agent.brokers.robinhood.broker_runtime import (
    RobinhoodRuntimeSession,
    open_robinhood_runtime,
)
from stock_agent.orchestration.robinhood_runtime_cycle import (
    RobinhoodEquityRuntimeCycleResult,
    run_robinhood_equity_cycle_from_runtime,
)
from stock_agent.orchestration.robinhood_strategy_cycle import (
    DEFAULT_ENTRY_BUDGET,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)


RuntimeOpener = Callable[
    ...,
    AbstractContextManager[
        RobinhoodRuntimeSession
    ],
]


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodEquityRuntimeRunOutcome:
    evaluated_at: datetime

    live_execution_requested: bool
    live_execution_enabled: bool

    cycle: RobinhoodEquityRuntimeCycleResult

    def __post_init__(
        self,
    ) -> None:
        if (
            self.live_execution_enabled
            and not self.live_execution_requested
        ):
            raise ValueError(
                "live execution cannot be enabled "
                "unless requested"
            )


def run_robinhood_equity_runtime_once(
    *,
    account_number: str,
    allowed_symbols: tuple[str, ...],
    universe_policy: EquityUniverseScreeningPolicy,
    not_found_grace_period: timedelta,
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
    env: dict[str, str] | None = None,
    runtime_opener: RuntimeOpener = (
        open_robinhood_runtime
    ),
    cycle_runner=(
        run_robinhood_equity_cycle_from_runtime
    ),
) -> RobinhoodEquityRuntimeRunOutcome:
    if not account_number.strip():
        raise ValueError(
            "account_number cannot be empty"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be "
            "timezone-aware"
        )

    if not allowed_symbols:
        raise ValueError(
            "allowed_symbols cannot be empty"
        )

    if budget <= Decimal("0"):
        raise ValueError(
            "budget must be positive"
        )

    with runtime_opener(
        account_number=account_number,
        not_found_grace_period=(
            not_found_grace_period
        ),
        env=env,
    ) as runtime:
        cycle = cycle_runner(
            runtime,
            allowed_symbols=(
                allowed_symbols
            ),
            universe_policy=(
                universe_policy
            ),
            evaluated_at=evaluated_at,
            budget=budget,
        )

        return (
            RobinhoodEquityRuntimeRunOutcome(
                evaluated_at=evaluated_at,
                live_execution_requested=(
                    runtime
                    .live_execution_requested
                ),
                live_execution_enabled=(
                    runtime
                    .live_execution_enabled
                ),
                cycle=cycle,
            )
        )