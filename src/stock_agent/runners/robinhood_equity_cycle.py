from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import Any

from stock_agent.brokers.robinhood.broker_runtime import (
    open_robinhood_runtime,
)
from stock_agent.orchestration.entry_placement_cycle import (
    EquityEntryExecutionMode,
)
from stock_agent.orchestration.robinhood_runtime_cycle import (
    run_robinhood_equity_cycle_from_runtime,
)
from stock_agent.orchestration.robinhood_strategy_cycle import (
    DEFAULT_ENTRY_BUDGET,
    RobinhoodEquityCycleRunOutcome,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightBlocker,
)
from stock_agent.orchestration.equity_entry_preflight_service import (
    EquityEntryPreflightBlockedError,
)


ROBINHOOD_ACCOUNT_NUMBER_ENV = (
    "ROBINHOOD_ACCOUNT_NUMBER"
)

ROBINHOOD_NOT_FOUND_GRACE_SECONDS_ENV = (
    "ROBINHOOD_NOT_FOUND_GRACE_SECONDS"
)


PRODUCTION_ALLOWED_SYMBOLS = (
    "SPY",
    "QQQ",
    "AAPL",
    "MSFT",
    "NVDA",
)


PRODUCTION_UNIVERSE_POLICY = (
    EquityUniverseScreeningPolicy(
        min_average_volume_30d=Decimal(
            "1000000"
        ),
        min_market_cap=Decimal(
            "1000000000"
        ),
    )
)


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def resolve_robinhood_account_number(
    env: Mapping[str, str] | None = None,
) -> str:
    source = (
        os.environ
        if env is None
        else env
    )

    raw = source.get(
        ROBINHOOD_ACCOUNT_NUMBER_ENV
    )

    if raw is None:
        raise ValueError(
            "ROBINHOOD_ACCOUNT_NUMBER "
            "is required"
        )

    account_number = raw.strip()

    if not account_number:
        raise ValueError(
            "ROBINHOOD_ACCOUNT_NUMBER "
            "must not be empty"
        )

    return account_number


def resolve_not_found_grace_period(
    env: Mapping[str, str] | None = None,
) -> timedelta:
    source = (
        os.environ
        if env is None
        else env
    )

    raw = source.get(
        ROBINHOOD_NOT_FOUND_GRACE_SECONDS_ENV
    )

    if raw is None:
        raise ValueError(
            "ROBINHOOD_NOT_FOUND_GRACE_SECONDS "
            "is required"
        )

    stripped = raw.strip()

    if not stripped:
        raise ValueError(
            "ROBINHOOD_NOT_FOUND_GRACE_SECONDS "
            "must not be empty"
        )

    try:
        seconds = int(
            stripped
        )
    except ValueError as exc:
        raise ValueError(
            "ROBINHOOD_NOT_FOUND_GRACE_SECONDS "
            "must be a non-negative integer"
        ) from exc

    if seconds < 0:
        raise ValueError(
            "ROBINHOOD_NOT_FOUND_GRACE_SECONDS "
            "must be a non-negative integer"
        )

    return timedelta(
        seconds=seconds
    )


def run_production_robinhood_equity_cycle(
    *,
    env: Mapping[str, str] | None = None,
    runtime_opener: Any = (
        open_robinhood_runtime
    ),
    cycle_runner: Any = (
        run_robinhood_equity_cycle_from_runtime
    ),
    clock: Any = _utc_now,
    budget: Decimal = (
        DEFAULT_ENTRY_BUDGET
    ),
) -> RobinhoodEquityCycleRunOutcome:
    source = (
        os.environ
        if env is None
        else env
    )

    account_number = (
        resolve_robinhood_account_number(
            source
        )
    )

    grace_period = (
        resolve_not_found_grace_period(
            source
        )
    )

    evaluated_at = clock()

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset()
        is None
    ):
        raise ValueError(
            "production clock must return "
            "timezone-aware datetime"
        )

    with runtime_opener(
        account_number=account_number,
        not_found_grace_period=(
            grace_period
        ),
        env=source,
    ) as runtime:
        if (
            runtime.live_execution_requested
            and not runtime.live_execution_enabled
        ):
            raise RuntimeError(
                "live execution was requested "
                "but startup safety recovery "
                "blocked live execution"
            )

        result = cycle_runner(
            runtime,
            allowed_symbols=(
                PRODUCTION_ALLOWED_SYMBOLS
            ),
            universe_policy=(
                PRODUCTION_UNIVERSE_POLICY
            ),
            evaluated_at=(
                evaluated_at
            ),
            budget=budget,
        )

    if result.placement_failure_count > 0:
        raise RuntimeError(
            "production equity entry cycle "
            "reported placement failure"
        )

    return result


def format_cycle_result(
    result: RobinhoodEquityCycleRunOutcome,
) -> str:
    if (
        result.execution_mode
        is EquityEntryExecutionMode.REVIEW_ONLY
    ):
        return (
            "EQUITY ENTRY CYCLE RESULT: "
            "REVIEW ONLY"
        )

    if result.placement_count > 0:
        return (
            "EQUITY ENTRY CYCLE RESULT: "
            "OPENING ORDER SUBMITTED"
        )

    return (
        "EQUITY ENTRY CYCLE RESULT: "
        "NO ACTION"
    )


def main() -> int:
    try:
        result = (
            run_production_robinhood_equity_cycle()
        )
    except EquityEntryPreflightBlockedError as exc:
        if (
            EquityEntryPreflightBlocker
            .DATA_UNAVAILABLE
            in exc.result.blockers
        ):
            raise

        print(
            "EQUITY ENTRY CYCLE RESULT: "
            "NO ACTION"
        )

        return 0

    print(
        format_cycle_result(
            result
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )