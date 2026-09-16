import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from stock_agent.brokers.robinhood import (
    GuardedRobinhoodBrokerClient,
    MCPRobinhoodBrokerClient,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodMarketHours,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.brokers.robinhood.connection import (
    open_robinhood_mcp_invoker,
)
from stock_agent.brokers.robinhood.placement_journal import (
    SQLitePlacementAttemptJournal,
)
from stock_agent.domain import AssetType


def unused_receipt_decoder(
    submission,
    raw_result,
):
    raise AssertionError(
        "receipt decoder must not be called "
        "during review-only smoke test"
    )


def main() -> None:
    account_number = os.environ.get(
        "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER"
    )

    symbol = os.environ.get(
        "ROBINHOOD_REVIEW_SYMBOL"
    )

    quantity_raw = os.environ.get(
        "ROBINHOOD_REVIEW_QUANTITY"
    )

    if not account_number:
        raise RuntimeError(
            "ROBINHOOD_AGENTIC_ACCOUNT_NUMBER "
            "is not set"
        )

    if not symbol:
        raise RuntimeError(
            "ROBINHOOD_REVIEW_SYMBOL is not set"
        )

    if not quantity_raw:
        raise RuntimeError(
            "ROBINHOOD_REVIEW_QUANTITY is not set"
        )

    quantity = Decimal(
        quantity_raw
    )

    if quantity <= 0:
        raise ValueError(
            "ROBINHOOD_REVIEW_QUANTITY "
            "must be positive"
        )

    submission = RobinhoodExitSubmission(
        request=RobinhoodExitOrderRequest(
            position_id=(
                "smoke-review-position"
            ),
            account_number=account_number,
            asset_type=AssetType.EQUITY,
            symbol=symbol.strip().upper(),
            quantity=quantity,
            action=(
                RobinhoodExitAction.EQUITY_SELL
            ),
            option_id=None,
        ),
        ref_id=str(uuid4()),
        order_type=(
            RobinhoodOrderType.MARKET
        ),
        time_in_force=(
            RobinhoodTimeInForce.GFD
        ),
        market_hours=(
            RobinhoodMarketHours.REGULAR_HOURS
        ),
        limit_price=None,
    )

    with tempfile.TemporaryDirectory() as directory:
        journal = SQLitePlacementAttemptJournal(
            Path(directory)
            / "placement-attempts.sqlite3"
        )

        journal.initialize()

        with open_robinhood_mcp_invoker(
            allowed_account_number=(
                account_number
            ),
            startup_timeout_seconds=300.0,
        ) as invoker:
            broker = MCPRobinhoodBrokerClient(
                invoker=invoker,
                receipt_decoder=(
                    unused_receipt_decoder
                ),
                placement_journal=journal,
            )

            guarded_broker = (
                GuardedRobinhoodBrokerClient(
                    broker,
                    live_enabled=False,
                )
            )

            review = (
                guarded_broker.review_exit_order(
                    submission
                )
            )

            print(
                "\nReal broker review succeeded."
            )

            print(
                "Approved:",
                review.approved,
            )

            print(
                "Alert count:",
                len(review.alerts),
            )

            for alert in review.alerts:
                print(
                    "-",
                    alert,
                )


if __name__ == "__main__":
    main()