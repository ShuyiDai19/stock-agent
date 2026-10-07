from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
)
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from stock_agent.brokers.robinhood.broker_runtime import (
    ROBINHOOD_LIVE_EXECUTION_ENV,
    STOCK_AGENT_RUNTIME_MODE_ENV,
    open_robinhood_runtime,
)
from stock_agent.brokers.robinhood.entry_execution_limits import (
    MAX_LIVE_DAILY_ENTRY_NOTIONAL,
)
from stock_agent.orchestration.equity_entry_preflight_service import (
    EquityEntryPreflightBlockedError,
    require_live_equity_entry_preflight,
)


class RobinhoodLiveReadinessStatus(
    StrEnum
):
    READY = "ready"
    BLOCKED = "blocked"


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodLiveReadinessResult:
    status: RobinhoodLiveReadinessStatus

    exit_recovery_clear: bool
    entry_recovery_clear: bool
    activation_clear: bool
    preflight_clear: bool
    daily_limit_clear: bool

    daily_reserved_notional: Decimal
    requested_order_notional: Decimal

    preflight_blockers: tuple[
        str,
        ...,
    ]

    blockers: tuple[
        str,
        ...,
    ]

    preflight_unavailable_sources: tuple[
        str,
        ...,
    ]

    @property
    def ready(
        self,
    ) -> bool:
        return (
            self.status
            is RobinhoodLiveReadinessStatus.READY
        )


def _safe_readiness_env(
    env: Mapping[str, str] | None,
) -> dict[str, str]:
    source = (
        {}
        if env is None
        else dict(env)
    )

    # A readiness probe must never acquire
    # broker execution capability.
    source[
        STOCK_AGENT_RUNTIME_MODE_ENV
    ] = "safe"

    source[
        ROBINHOOD_LIVE_EXECUTION_ENV
    ] = "false"

    return source


def check_robinhood_live_readiness(
    *,
    account_number: str,
    evaluated_at: datetime,
    not_found_grace_period: timedelta,
    requested_order_notional: Decimal,
    minimum_cash_reserve: Decimal = (
        Decimal("5")
    ),
    env: Mapping[str, str] | None = None,
    runtime_opener=(
        open_robinhood_runtime
    ),
) -> RobinhoodLiveReadinessResult:
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

    if (
        not requested_order_notional.is_finite()
        or requested_order_notional
        <= Decimal("0")
    ):
        raise ValueError(
            "requested_order_notional must "
            "be positive and finite"
        )

    blockers: list[str] = []

    preflight_blockers: tuple[
        str,
        ...,
    ] = ()

    preflight_unavailable_sources: tuple[
        str,
        ...,
    ] = ()

    safe_env = _safe_readiness_env(
        env
    )

    with runtime_opener(
        account_number=account_number,
        not_found_grace_period=(
            not_found_grace_period
        ),
        env=safe_env,
    ) as runtime:
        # Structural safety invariant:
        # this probe must never receive an
        # entry placement capability.
        if runtime.live_execution_enabled:
            raise RuntimeError(
                "readiness runtime unexpectedly "
                "enabled live execution"
            )

        if runtime.entry_placer is not None:
            raise RuntimeError(
                "readiness runtime unexpectedly "
                "exposed entry placer"
            )

        #
        # 1. Exit-side startup recovery
        #
        exit_recovery_clear = (
            not runtime.recovery
            .has_unresolved_attempts
        )

        if not exit_recovery_clear:
            blockers.append(
                "unresolved exit placement "
                "recovery"
            )

        #
        # 2. Entry-side placement recovery
        #
        entry_recovery_clear = True

        try:
            recovery_results = (
                runtime
                .entry_recovery_service
                .recover(
                    account_number=(
                        account_number
                    )
                )
            )

            if any(
                not result.recovered
                for result
                in recovery_results
            ):
                entry_recovery_clear = False

                blockers.append(
                    "unresolved entry placement "
                    "recovery"
                )

        except Exception:
            entry_recovery_clear = False

            blockers.append(
                "entry placement recovery "
                "failed"
            )

        #
        # 3. ACKNOWLEDGED → ACTIVE
        # reconciliation
        #
        activation_clear = True

        if entry_recovery_clear:
            try:
                runtime\
                    .entry_activation_reconciler\
                    .reconcile(
                        account_number=(
                            account_number
                        )
                    )

            except Exception:
                activation_clear = False

                blockers.append(
                    "entry activation "
                    "reconciliation failed"
                )
        else:
            activation_clear = False

        #
        # 4. Broker/account preflight
        #
        preflight_clear = True

        if (
            entry_recovery_clear
            and activation_clear
        ):
            try:
                require_live_equity_entry_preflight(
                    runtime
                    .entry_preflight_reader,
                    account_number=(
                        account_number
                    ),
                    evaluated_at=(
                        evaluated_at
                    ),
                    opening_debit=(
                        requested_order_notional
                    ),
                    minimum_cash_reserve=(
                        minimum_cash_reserve
                    ),
                )

            except EquityEntryPreflightBlockedError as error:
                preflight_clear = False

                preflight_blockers = tuple(
                    blocker.value
                    for blocker
                    in error.result.blockers
                )

                preflight_unavailable_sources = tuple(
                    source.value
                    for source
                    in error.result.unavailable_sources
                )

                if preflight_blockers:
                    blockers.extend(
                        (
                            "live entry preflight: "
                            f"{blocker}"
                        )
                        for blocker
                        in preflight_blockers
                    )
                else:
                    blockers.append(
                        "live entry preflight "
                        "blocked"
                    )

            except Exception:
                preflight_clear = False

                blockers.append(
                    "live entry preflight "
                    "failed"
                )
        else:
            preflight_clear = False

        #
        # 5. Persistent daily limit
        #
        daily_reserved_notional = (
            runtime
            .entry_placement_journal
            .daily_reserved_notional(
                account_number=(
                    account_number
                ),
                as_of=evaluated_at,
            )
        )

        daily_limit_clear = (
            daily_reserved_notional
            + requested_order_notional
            <= MAX_LIVE_DAILY_ENTRY_NOTIONAL
        )

        if not daily_limit_clear:
            blockers.append(
                "daily live entry notional "
                "limit exhausted"
            )

    ready = (
        exit_recovery_clear
        and entry_recovery_clear
        and activation_clear
        and preflight_clear
        and daily_limit_clear
    )

    return RobinhoodLiveReadinessResult(
        status=(
            RobinhoodLiveReadinessStatus.READY
            if ready
            else RobinhoodLiveReadinessStatus.BLOCKED
        ),
        exit_recovery_clear=(
            exit_recovery_clear
        ),
        entry_recovery_clear=(
            entry_recovery_clear
        ),
        activation_clear=(
            activation_clear
        ),
        preflight_clear=(
            preflight_clear
        ),
        daily_limit_clear=(
            daily_limit_clear
        ),
        daily_reserved_notional=(
            daily_reserved_notional
        ),
        requested_order_notional=(
            requested_order_notional
        ),
        preflight_blockers=(
            preflight_blockers
        ),
        blockers=tuple(
            blockers
        ),
        preflight_unavailable_sources=(
            preflight_unavailable_sources
        ),
    )