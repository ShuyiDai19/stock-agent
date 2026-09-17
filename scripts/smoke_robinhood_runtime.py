import logging
import os
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from stock_agent.brokers.robinhood.broker_runtime import (
    open_robinhood_runtime,
)
from stock_agent.brokers.robinhood.errors import (
    LiveExecutionDisabledError,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodMarketHours,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.domain import AssetType


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
    )

    account_number = os.environ.get(
        "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER"
    )

    if not account_number:
        raise RuntimeError(
            "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER "
            "must be set"
        )

    symbol = os.environ.get(
        "ROBINHOOD_REVIEW_SYMBOL",
        "AAPL",
    )

    quantity = Decimal(
        os.environ.get(
            "ROBINHOOD_REVIEW_QUANTITY",
            "0.001",
        )
    )

    # Preserve useful environment configuration,
    # but force this smoke test into safe mode.
    runtime_env = dict(os.environ)

    runtime_env[
        "STOCK_AGENT_RUNTIME_MODE"
    ] = "safe"

    runtime_env[
        "ROBINHOOD_LIVE_EXECUTION_ENABLED"
    ] = "false"

    submission = RobinhoodExitSubmission(
        request=RobinhoodExitOrderRequest(
            position_id="runtime-smoke-position",
            account_number=account_number,
            asset_type=AssetType.EQUITY,
            symbol=symbol,
            quantity=quantity,
            action=(
                RobinhoodExitAction.EQUITY_SELL
            ),
            option_id=None,
        ),
        ref_id=str(uuid4()),
        order_type=RobinhoodOrderType.MARKET,
        time_in_force=(
            RobinhoodTimeInForce.GFD
        ),
        market_hours=(
            RobinhoodMarketHours.REGULAR_HOURS
        ),
        limit_price=None,
    )

    with open_robinhood_runtime(
        account_number=account_number,
        not_found_grace_period=(
            timedelta(minutes=5)
        ),
        env=runtime_env,
        startup_timeout_seconds=300.0,
    ) as runtime:
        print(
            "Robinhood production runtime "
            "connected successfully."
        )

        print(
            "Recovery results:",
            len(runtime.recovery.results),
        )

        print(
            "Unresolved placement attempts:",
            runtime.recovery
            .unresolved_attempt_count,
        )

        print(
            "Live execution requested:",
            runtime.live_execution_requested,
        )

        print(
            "Live execution enabled:",
            runtime.live_execution_enabled,
        )

        if runtime.live_execution_requested:
            raise AssertionError(
                "safe-mode smoke unexpectedly "
                "requested live execution"
            )

        if runtime.live_execution_enabled:
            raise AssertionError(
                "safe-mode smoke unexpectedly "
                "enabled live execution"
            )

        review = (
            runtime.broker.review_exit_order(
                submission
            )
        )

        print(
            "Real MCP review completed."
        )

        print(
            "Review approved:",
            review.approved,
        )

        print(
            "Review alert count:",
            len(review.alerts),
        )

        try:
            runtime.broker.submit_exit_order(
                submission
            )
        except LiveExecutionDisabledError:
            print(
                "Live submit correctly blocked."
            )
        else:
            raise AssertionError(
                "live submission was not blocked"
            )


if __name__ == "__main__":
    main()