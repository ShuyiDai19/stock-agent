import argparse
import os
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.broker_runtime import (
    build_startup_safety_summary,
    open_robinhood_runtime,
)
from stock_agent.orchestration.equity_entry_smoke import (
    build_deterministic_equity_smoke_loader,
)
from stock_agent.orchestration.robinhood_runtime_cycle import (
    run_robinhood_equity_cycle_from_runtime,
)
from stock_agent.runners.robinhood_equity_cycle import (
    PRODUCTION_ALLOWED_SYMBOLS,
    PRODUCTION_UNIVERSE_POLICY,
    format_cycle_result,
    format_entry_rejection_diagnostics,
    format_no_action_diagnostics,
    resolve_mcp_startup_timeout_seconds,
    resolve_not_found_grace_period,
    resolve_robinhood_account_number,
)


SMOKE_BUDGET = Decimal("8")

ARMING_PHRASE = (
    "PLACE ONE REAL $8 EQUITY BUY"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run one deterministic live equity "
            "entry smoke test."
        )
    )

    parser.add_argument(
        "--symbol",
        required=True,
        help=(
            "One symbol already present in the "
            "production allowlist."
        ),
    )

    return parser.parse_args()


def require_smoke_symbol(
    symbol: str,
) -> str:
    normalized = (
        symbol.strip().upper()
    )

    if not normalized:
        raise ValueError(
            "smoke symbol cannot be empty"
        )

    if (
        normalized
        not in PRODUCTION_ALLOWED_SYMBOLS
    ):
        raise ValueError(
            "smoke symbol must already be in "
            "PRODUCTION_ALLOWED_SYMBOLS"
        )

    return normalized


def require_live_arming() -> None:
    print()
    print(
        "WARNING: this smoke test can submit "
        "one REAL equity BUY."
    )
    print(
        f"Maximum intended opening debit: "
        f"${SMOKE_BUDGET}"
    )
    print()
    print(
        "Type exactly:"
    )
    print(
        ARMING_PHRASE
    )

    entered = input(
        "> "
    )

    if entered != ARMING_PHRASE:
        raise RuntimeError(
            "live smoke test was not armed"
        )


def main() -> int:
    args = parse_args()

    symbol = require_smoke_symbol(
        args.symbol
    )

    env = os.environ

    safety = (
        build_startup_safety_summary(
            env
        )
    )

    if not safety.live_execution_enabled:
        raise RuntimeError(
            "live smoke requires "
            "STOCK_AGENT_RUNTIME_MODE=live "
            "and "
            "ROBINHOOD_LIVE_EXECUTION_ENABLED=true"
        )

    account_number = (
        resolve_robinhood_account_number(
            env
        )
    )

    grace_period = (
        resolve_not_found_grace_period(
            env
        )
    )

    startup_timeout_seconds = (
        resolve_mcp_startup_timeout_seconds(
            env
        )
    )

    candidate_loader = (
        build_deterministic_equity_smoke_loader(
            smoke_symbol=symbol,
        )
    )

    require_live_arming()

    with open_robinhood_runtime(
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
                "startup recovery blocked "
                "live execution"
            )

        if not runtime.live_execution_enabled:
            raise RuntimeError(
                "smoke test requires a live runtime"
            )

        # Deliberately evaluate AFTER OAuth/runtime startup.
        # Otherwise a long interactive OAuth flow can make
        # quote timestamps appear to be from the future.
        evaluated_at = datetime.now(
            timezone.utc
        )

        result = (
            run_robinhood_equity_cycle_from_runtime(
                runtime,
                allowed_symbols=(
                    symbol,
                ),
                universe_policy=(
                    PRODUCTION_UNIVERSE_POLICY
                ),
                evaluated_at=(
                    evaluated_at
                ),
                budget=(
                    SMOKE_BUDGET
                ),
                candidate_loader=(
                    candidate_loader
                ),
            )
        )

    if result.placement_failure_count > 0:
        raise RuntimeError(
            "equity smoke cycle reported "
            "placement failure"
        )

    formatted = format_cycle_result(
        result
    )

    print(
        formatted
    )

    if (
        formatted
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

    if result.entry_order_submitted:
        print()
        print(
            "SMOKE ORDER SUBMITTED."
        )
        print(
            "Do not run this smoke command "
            "again until fill/activation "
            "reconciliation is verified."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )