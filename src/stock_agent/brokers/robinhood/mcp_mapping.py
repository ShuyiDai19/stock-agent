from dataclasses import dataclass
from typing import Any

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.domain import AssetType


@dataclass(frozen=True)
class RobinhoodMCPToolCall:
    tool_name: str
    arguments: dict[str, Any]


def build_robinhood_mcp_review_call(
    submission: RobinhoodExitSubmission,
) -> RobinhoodMCPToolCall:
    request = submission.request

    if request.asset_type is AssetType.EQUITY:
        if request.action is not RobinhoodExitAction.EQUITY_SELL:
            raise ValueError(
                "equity exit must use equity sell action"
            )

        arguments: dict[str, Any] = {
            "account_number": request.account_number,
            "symbol": request.symbol,
            "side": "sell",
            "type": submission.order_type.value,
            "quantity": str(request.quantity),
            "time_in_force": submission.time_in_force.value,
            "market_hours": submission.market_hours.value,
        }

        if submission.order_type is RobinhoodOrderType.LIMIT:
            arguments["limit_price"] = str(
                submission.limit_price
            )

        return RobinhoodMCPToolCall(
            tool_name="review_equity_order",
            arguments=arguments,
        )

    if request.asset_type is AssetType.OPTION:
        if (
            request.action
            is not RobinhoodExitAction.OPTION_SELL_TO_CLOSE
        ):
            raise ValueError(
                "option exit must use sell-to-close action"
            )

        if submission.order_type is not RobinhoodOrderType.LIMIT:
            raise ValueError(
                "option exit submission must use limit order"
            )

        if request.option_id is None:
            raise ValueError(
                "option exit requires option_id"
            )

        return RobinhoodMCPToolCall(
            tool_name="review_option_order",
            arguments={
                "account_number": request.account_number,
                "legs": [
                    {
                        "option_id": request.option_id,
                        "side": "sell",
                        "position_effect": "close",
                        "ratio_quantity": 1,
                    }
                ],
                "type": "limit",
                "quantity": str(request.quantity),
                "price": str(submission.limit_price),
                "time_in_force": submission.time_in_force.value,
                "market_hours": submission.market_hours.value,
                "chain_symbol": request.symbol,
                "underlying_type": "equity",
            },
        )

    raise ValueError(
        f"unsupported asset type: {request.asset_type}"
    )

def build_robinhood_mcp_place_call(
    submission: RobinhoodExitSubmission,
) -> RobinhoodMCPToolCall:
    request = submission.request

    if request.asset_type is AssetType.EQUITY:
        if request.action is not RobinhoodExitAction.EQUITY_SELL:
            raise ValueError(
                "equity exit must use equity sell action"
            )

        arguments: dict[str, Any] = {
            "account_number": request.account_number,
            "symbol": request.symbol,
            "side": "sell",
            "type": submission.order_type.value,
            "quantity": str(request.quantity),
            "time_in_force": submission.time_in_force.value,
            "market_hours": submission.market_hours.value,
            "ref_id": submission.ref_id,
        }

        if submission.order_type is RobinhoodOrderType.LIMIT:
            arguments["limit_price"] = str(
                submission.limit_price
            )

        return RobinhoodMCPToolCall(
            tool_name="place_equity_order",
            arguments=arguments,
        )

    if request.asset_type is AssetType.OPTION:
        if (
            request.action
            is not RobinhoodExitAction.OPTION_SELL_TO_CLOSE
        ):
            raise ValueError(
                "option exit must use sell-to-close action"
            )

        if submission.order_type is not RobinhoodOrderType.LIMIT:
            raise ValueError(
                "option exit submission must use limit order"
            )

        if request.option_id is None:
            raise ValueError(
                "option exit requires option_id"
            )

        return RobinhoodMCPToolCall(
            tool_name="place_option_order",
            arguments={
                "account_number": request.account_number,
                "legs": [
                    {
                        "option_id": request.option_id,
                        "side": "sell",
                        "position_effect": "close",
                        "ratio_quantity": 1,
                    }
                ],
                "type": "limit",
                "quantity": str(request.quantity),
                "price": str(submission.limit_price),
                "time_in_force": submission.time_in_force.value,
                "market_hours": submission.market_hours.value,
                "ref_id": submission.ref_id,
            },
        )

    raise ValueError(
        f"unsupported asset type: {request.asset_type}"
    )