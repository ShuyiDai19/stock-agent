from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from stock_agent.domain import AssetType
from stock_agent.execution import ExitIntent


class RobinhoodExitAction(str, Enum):
    EQUITY_SELL = "equity_sell"
    OPTION_SELL_TO_CLOSE = "option_sell_to_close"


@dataclass(frozen=True)
class RobinhoodExitOrderRequest:
    position_id: str
    account_number: str
    asset_type: AssetType
    symbol: str
    quantity: Decimal
    action: RobinhoodExitAction
    option_id: str | None = None


def build_robinhood_exit_order_request(
    intent: ExitIntent,
) -> RobinhoodExitOrderRequest:
    if intent.asset_type is AssetType.EQUITY:
        if intent.option_id is not None:
            raise ValueError(
                "equity exit intent cannot contain option_id"
            )

        return RobinhoodExitOrderRequest(
            position_id=intent.position_id,
            account_number=intent.account_number,
            asset_type=intent.asset_type,
            symbol=intent.symbol,
            quantity=intent.quantity,
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

    if intent.asset_type is AssetType.OPTION:
        if intent.option_id is None or not intent.option_id.strip():
            raise ValueError(
                "option exit intent requires option_id"
            )

        if intent.quantity != intent.quantity.to_integral_value():
            raise ValueError(
                "option exit quantity must be whole contracts"
            )

        return RobinhoodExitOrderRequest(
            position_id=intent.position_id,
            account_number=intent.account_number,
            asset_type=intent.asset_type,
            symbol=intent.symbol,
            quantity=intent.quantity,
            action=RobinhoodExitAction.OPTION_SELL_TO_CLOSE,
            option_id=intent.option_id,
        )

    raise ValueError(
        f"unsupported asset type: {intent.asset_type}"
    )