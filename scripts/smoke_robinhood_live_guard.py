import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from stock_agent.brokers.robinhood import (
    GuardedRobinhoodBrokerClient,
    LiveExecutionDisabledError,
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
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.placement_journal import (
    SQLitePlacementAttemptJournal,
)
from stock_agent.domain import AssetType


class RecordingMCPToolInvoker:
    def __init__(
        self,
        invoker: MCPToolInvoker,
    ) -> None:
        self._invoker = invoker
        self.tool_names: list[str] = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.tool_names.append(
            tool_name
        )

        return self._invoker.call_tool(
            tool_name,
            arguments,
        )


def unused_receipt_decoder(
    submission,
    raw_result,
):
    raise AssertionError(
        "receipt decoder must not be called "
        "when live execution is disabled"
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
                "smoke-live-guard-position"
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
            recording_invoker = (
                RecordingMCPToolInvoker(
                    invoker
                )
            )

            broker = MCPRobinhoodBrokerClient(
                recording_invoker,
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
                "\nReview approved:",
                review.approved,
            )

            try:
                guarded_broker.submit_exit_order(
                    submission
                )
            except LiveExecutionDisabledError:
                print(
                    "Live execution correctly blocked."
                )
            else:
                raise AssertionError(
                    "submit_exit_order unexpectedly "
                    "succeeded while live execution "
                    "was disabled"
                )

            # Verify that no real place_* MCP tool was called.
            place_calls = [
                name
                for name in recording_invoker.tool_names
                if name.startswith("place_")
            ]

            if place_calls:
                raise AssertionError(
                    "live guard failed: "
                    "a place tool reached MCP"
                )

            print(
                "MCP tool calls:",
                recording_invoker.tool_names,
            )

            print(
                "Verified: no place_* tool "
                "reached Robinhood MCP."
            )

            # Verify that execution was blocked before the
            # placement journal boundary was crossed.
            persisted = journal.get(
                submission.ref_id
            )

            if persisted is not None:
                raise AssertionError(
                    "disabled live execution unexpectedly "
                    "created a placement journal record"
                )

            print(
                "Verified: no placement attempt "
                "was persisted."
            )


if __name__ == "__main__":
    main()