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
    RobinhoodEquityRuntimeCycleResult,
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

ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS_ENV = (
    "ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS"
)

DEFAULT_ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS = 10


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

def resolve_mcp_startup_timeout_seconds(
    env=None,
) -> int:
    source = (
        os.environ
        if env is None
        else env
    )

    raw_value = source.get(
        ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS_ENV
    )

    if raw_value is None:
        return (
            DEFAULT_ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS
        )

    stripped = raw_value.strip()

    try:
        value = int(
            stripped
        )
    except ValueError as error:
        raise ValueError(
            "ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS "
            "must be a positive integer"
        ) from error

    if value <= 0:
        raise ValueError(
            "ROBINHOOD_MCP_STARTUP_TIMEOUT_SECONDS "
            "must be a positive integer"
        )

    return value

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

    startup_timeout_seconds = (
        resolve_mcp_startup_timeout_seconds(
            source
        )
    )

    with runtime_opener(
        account_number=account_number,
        not_found_grace_period=(
            grace_period
        ),
        env=env,
        startup_timeout_seconds=(
            startup_timeout_seconds
        ),
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
    result,
) -> str:
    if result.exit_order_submitted:
        return (
            "EQUITY ENTRY CYCLE RESULT: "
            "CLOSING ORDER SUBMITTED"
        )

    if result.exit_previewed:
        return (
            "EQUITY ENTRY CYCLE RESULT: "
            "REVIEW ONLY"
        )

    entry_result = result.entry_result

    if entry_result is None:
        raise RuntimeError(
            "runtime cycle result is missing "
            "entry result after no-action exit"
        )

    if (
        entry_result.execution_mode
        is EquityEntryExecutionMode.REVIEW_ONLY
    ):
        return (
            "EQUITY ENTRY CYCLE RESULT: "
            "REVIEW ONLY"
        )

    if result.entry_order_submitted:
        return (
            "EQUITY ENTRY CYCLE RESULT: "
            "OPENING ORDER SUBMITTED"
        )

    return (
        "EQUITY ENTRY CYCLE RESULT: "
        "NO ACTION"
    )

def format_no_action_diagnostics(
    result,
) -> str:
    entry_result = getattr(
        result,
        "entry_result",
        result,
    )

    if entry_result is None:
        return (
            "EQUITY ENTRY DIAGNOSTICS: "
            "entry_result=none"
        )

    return (
        "EQUITY ENTRY DIAGNOSTICS: "
        f"universe_selected="
        f"{len(getattr(entry_result, 'universe_eligible_symbols', ()))} "
        f"universe_rejected="
        f"{getattr(entry_result, 'universe_rejected_count', 0)} "
        f"universe_errors="
        f"{getattr(entry_result, 'universe_error_count', 0)} "
        f"loaded_candidates="
        f"{getattr(entry_result, 'loaded_candidate_count', 0)} "
        f"eligible_entries="
        f"{getattr(entry_result, 'eligible_entry_count', 0)} "
        f"market_data_errors="
        f"{getattr(entry_result, 'market_data_error_count', 0)} "
        f"review_errors="
        f"{getattr(entry_result, 'review_error_count', 0)} "
        f"placement_blocked="
        f"{getattr(entry_result, 'placement_blocked_count', 0)}"
    )

def format_entry_rejection_diagnostics(
    result,
) -> tuple[str, ...]:
    entry_result = getattr(
        result,
        "entry_result",
        None,
    )

    if entry_result is None:
        return ()

    cycle = getattr(
        entry_result,
        "cycle",
        None,
    )

    if cycle is None:
        return ()

    strategy = getattr(
        cycle,
        "strategy",
        None,
    )

    if strategy is None:
        return ()

    lines = []

    for item in strategy.items:
        if item.error is not None:
            lines.append(
                (
                    "ENTRY REJECTION: "
                    f"{item.symbol} "
                    "error="
                    f"{type(item.error).__name__}"
                )
            )

            continue

        outcome = item.outcome

        if outcome is None:
            continue

        if outcome.eligible_to_place:
            continue

        confirmation_reasons = sorted(
            reason.value
            for reason
            in outcome
            .decision
            .confirmation
            .reasons
        )

        risk_reasons = sorted(
            reason.value
            for reason
            in outcome
            .decision
            .risk
            .reasons
        )

        details = []

        if confirmation_reasons:
            details.append(
                (
                    "confirmation="
                    + ",".join(
                        confirmation_reasons
                    )
                )
            )

        if risk_reasons:
            details.append(
                (
                    "risk="
                    + ",".join(
                        risk_reasons
                    )
                )
            )

        if (
            not confirmation_reasons
            and not risk_reasons
            and outcome.reason
        ):
            details.append(
                (
                    f"stage="
                    f"{outcome.status.value}"
                )
            )
            details.append(
                (
                    f"reason="
                    f"{outcome.reason}"
                )
            )

        if not details:
            details.append(
                (
                    f"stage="
                    f"{outcome.status.value}"
                )
            )

        lines.append(
            (
                "ENTRY REJECTION: "
                f"{item.symbol} "
                + " ".join(
                    details
                )
            )
        )

    return tuple(
        lines
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

    formatted_result = (
        format_cycle_result(
            result
        )
    )

    print(
        formatted_result
    )

    if (
        formatted_result
        == (
            "EQUITY ENTRY CYCLE RESULT: "
            "NO ACTION"
        )
    ):
        print(
            format_no_action_diagnostics(
                result
            )
        )

        for line in (
            format_entry_rejection_diagnostics(
                result
            )
        ):
            print(
                line
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )