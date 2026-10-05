from __future__ import annotations

import argparse
import os

from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import (
    Decimal,
    InvalidOperation,
)
from enum import StrEnum

from stock_agent.orchestration.robinhood_runtime_runner import (
    RobinhoodEquityRuntimeRunOutcome,
    run_robinhood_equity_runtime_once,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreeningPolicy,
)


class RobinhoodOperatorMode(
    StrEnum
):
    SAFE = "safe"
    LIVE = "live"


Clock = Callable[[], datetime]


def _positive_decimal(
    raw: str,
) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(
            "must be a valid decimal"
        ) from exc

    if (
        not value.is_finite()
        or value <= Decimal("0")
    ):
        raise argparse.ArgumentTypeError(
            "must be positive and finite"
        )

    return value


def _non_negative_int(
    raw: str,
) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be an integer"
        ) from exc

    if value < 0:
        raise argparse.ArgumentTypeError(
            "must be non-negative"
        )

    return value


def build_parser(
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robinhood-equity-once",
        description=(
            "Run one Robinhood equity runtime "
            "cycle."
        ),
    )

    parser.add_argument(
        "--account-number",
        required=True,
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
    )

    parser.add_argument(
        "--mode",
        choices=tuple(
            mode.value
            for mode in RobinhoodOperatorMode
        ),
        default=(
            RobinhoodOperatorMode
            .SAFE
            .value
        ),
    )

    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help=(
            "Required together with "
            "--mode live."
        ),
    )

    parser.add_argument(
        "--budget",
        type=_positive_decimal,
        default=DEFAULT_ENTRY_BUDGET,
    )

    parser.add_argument(
        "--minimum-average-volume",
        type=_positive_decimal,
        default=Decimal("1000000"),
    )

    parser.add_argument(
        "--minimum-market-cap",
        type=_positive_decimal,
        default=Decimal("1000000000"),
    )

    parser.add_argument(
        "--not-found-grace-seconds",
        type=_non_negative_int,
        default=120,
    )

    return parser


def build_runtime_env(
    *,
    mode: RobinhoodOperatorMode,
    base_env: Mapping[str, str],
) -> dict[str, str]:
    env = dict(base_env)

    if mode is RobinhoodOperatorMode.LIVE:
        env[
            "STOCK_AGENT_RUNTIME_MODE"
        ] = "live"

        env[
            "ROBINHOOD_LIVE_EXECUTION_ENABLED"
        ] = "true"

        return env

    env[
        "STOCK_AGENT_RUNTIME_MODE"
    ] = "safe"

    env[
        "ROBINHOOD_LIVE_EXECUTION_ENABLED"
    ] = "false"

    return env


def _normalize_symbols(
    raw_symbols: Sequence[str],
) -> tuple[str, ...]:
    symbols = tuple(
        symbol.strip().upper()
        for symbol in raw_symbols
        if symbol.strip()
    )

    if not symbols:
        raise ValueError(
            "at least one symbol is required"
        )

    if len(set(symbols)) != len(symbols):
        raise ValueError(
            "symbols must not contain duplicates"
        )

    return symbols


def run_operator_command(
    argv: Sequence[str] | None = None,
    *,
    runner=(
        run_robinhood_equity_runtime_once
    ),
    clock: Clock | None = None,
    environ: (
        Mapping[str, str]
        | None
    ) = None,
) -> RobinhoodEquityRuntimeRunOutcome:
    parser = build_parser()

    args = parser.parse_args(
        argv
    )

    mode = RobinhoodOperatorMode(
        args.mode
    )

    if (
        mode is RobinhoodOperatorMode.LIVE
        and not args.confirm_live
    ):
        parser.error(
            "--mode live requires "
            "--confirm-live"
        )

    if (
        mode is RobinhoodOperatorMode.SAFE
        and args.confirm_live
    ):
        parser.error(
            "--confirm-live may only be used "
            "with --mode live"
        )

    account_number = (
        args.account_number.strip()
    )

    if not account_number:
        parser.error(
            "account number cannot be empty"
        )

    try:
        symbols = _normalize_symbols(
            args.symbols
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    source_env = (
        os.environ
        if environ is None
        else environ
    )

    runtime_env = build_runtime_env(
        mode=mode,
        base_env=source_env,
    )

    effective_clock = (
        clock
        if clock is not None
        else (
            lambda: datetime.now(
                timezone.utc
            )
        )
    )

    evaluated_at = (
        effective_clock()
    )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset()
        is None
    ):
        raise ValueError(
            "operator clock must return "
            "timezone-aware datetime"
        )

    universe_policy = (
        EquityUniverseScreeningPolicy(
            min_average_volume_30d=(
                args.minimum_average_volume
            ),
            min_market_cap=(
                args.minimum_market_cap
            ),
        )
    )

    return runner(
        account_number=account_number,
        allowed_symbols=symbols,
        universe_policy=(
            universe_policy
        ),
        not_found_grace_period=(
            timedelta(
                seconds=(
                    args
                    .not_found_grace_seconds
                )
            )
        ),
        evaluated_at=evaluated_at,
        budget=args.budget,
        env=runtime_env,
    )


def format_operator_result(
    outcome: RobinhoodEquityRuntimeRunOutcome,
) -> str:
    cycle = outcome.cycle

    return "\n".join(
        (
            "Robinhood equity runtime run",
            (
                "live requested: "
                f"{outcome.live_execution_requested}"
            ),
            (
                "live enabled: "
                f"{outcome.live_execution_enabled}"
            ),
            (
                "exit submitted: "
                f"{cycle.exit_order_submitted}"
            ),
            (
                "entry placements: "
                f"{cycle.placement_count}"
            ),
            (
                "entry placement failures: "
                f"{cycle.placement_failure_count}"
            ),
        )
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    outcome = run_operator_command(
        argv
    )

    print(
        format_operator_result(
            outcome
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )