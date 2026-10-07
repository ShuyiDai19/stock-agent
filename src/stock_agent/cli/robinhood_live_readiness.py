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

from stock_agent.brokers.robinhood.entry_execution_limits import (
    MAX_LIVE_ENTRY_ORDER_NOTIONAL,
)
from stock_agent.orchestration.robinhood_live_readiness import (
    RobinhoodLiveReadinessResult,
    check_robinhood_live_readiness,
)


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
        prog="robinhood-live-readiness",
        description=(
            "Check whether Robinhood equity "
            "LIVE entry execution would be "
            "safe to arm. This command never "
            "enables live execution."
        ),
    )

    parser.add_argument(
        "--account-number",
        required=True,
    )

    parser.add_argument(
        "--order-notional",
        type=_positive_decimal,
        default=(
            MAX_LIVE_ENTRY_ORDER_NOTIONAL
        ),
    )

    parser.add_argument(
        "--minimum-cash-reserve",
        type=_positive_decimal,
        default=Decimal("5"),
    )

    parser.add_argument(
        "--not-found-grace-seconds",
        type=_non_negative_int,
        default=120,
    )

    return parser


def run_readiness_command(
    argv: Sequence[str] | None = None,
    *,
    checker=(
        check_robinhood_live_readiness
    ),
    clock: Clock | None = None,
    environ: (
        Mapping[str, str]
        | None
    ) = None,
) -> RobinhoodLiveReadinessResult:
    parser = build_parser()

    args = parser.parse_args(
        argv
    )

    account_number = (
        args.account_number.strip()
    )

    if not account_number:
        parser.error(
            "account number cannot be empty"
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
            "readiness clock must return "
            "timezone-aware datetime"
        )

    source_env = (
        os.environ
        if environ is None
        else environ
    )

    return checker(
        account_number=account_number,
        evaluated_at=evaluated_at,
        not_found_grace_period=(
            timedelta(
                seconds=(
                    args
                    .not_found_grace_seconds
                )
            )
        ),
        requested_order_notional=(
            args.order_notional
        ),
        minimum_cash_reserve=(
            args.minimum_cash_reserve
        ),
        # Pass the real environment through so
        # journal/state path configuration is
        # preserved. The readiness service itself
        # force-overrides execution mode to SAFE.
        env=dict(
            source_env
        ),
    )


def format_readiness_result(
    result: RobinhoodLiveReadinessResult,
) -> str:
    lines = [
        "Robinhood live readiness",
        (
            "status: "
            f"{result.status.value.upper()}"
        ),
        (
            "exit recovery clear: "
            f"{result.exit_recovery_clear}"
        ),
        (
            "entry recovery clear: "
            f"{result.entry_recovery_clear}"
        ),
        (
            "activation clear: "
            f"{result.activation_clear}"
        ),
        (
            "preflight clear: "
            f"{result.preflight_clear}"
        ),
    ]

    if result.preflight_blockers:
        lines.append(
            "preflight blockers:"
        )

        lines.extend(
            f"- {blocker}"
            for blocker
            in result.preflight_blockers
        )
    else:
        lines.append(
            "preflight blockers: none"
        )

    if result.preflight_unavailable_sources:
        lines.append(
            "preflight unavailable sources:"
        )

        lines.extend(
            f"- {source}"
            for source
            in result.preflight_unavailable_sources
        )
    else:
        lines.append(
            "preflight unavailable sources: none"
        )

    lines.extend(
        [
            (
                "daily limit clear: "
                f"{result.daily_limit_clear}"
            ),
            (
                "daily reserved notional: $"
                f"{result.daily_reserved_notional}"
            ),
            (
                "requested order notional: $"
                f"{result.requested_order_notional}"
            ),
        ]
    )

    if result.blockers:
        lines.append(
            "blockers:"
        )

        lines.extend(
            f"- {blocker}"
            for blocker in result.blockers
        )
    else:
        lines.append(
            "blockers: none"
        )

    return "\n".join(
        lines
    )

    if result.preflight_blockers:
        lines.append(
            "preflight blockers:"
        )

        lines.extend(
            f"- {blocker}"
            for blocker
            in result.preflight_blockers
        )
    else:
        lines.append(
            "preflight blockers: none"
        )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    result = run_readiness_command(
        argv
    )

    print(
        format_readiness_result(
            result
        )
    )

    if result.ready:
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )