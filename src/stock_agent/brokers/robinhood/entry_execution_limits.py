from decimal import (
    Decimal,
    InvalidOperation,
)

from stock_agent.strategy.entry_execution import (
    EquityEntryExecutionMode,
    EquityEntryExecutionPlan,
)


MAX_LIVE_ENTRY_ORDER_NOTIONAL = Decimal(
    "5"
)

MAX_LIVE_DAILY_ENTRY_NOTIONAL = Decimal(
    "10"
)


class EquityEntryOrderLimitExceededError(
    RuntimeError
):
    pass


class EquityEntryDailyLimitExceededError(
    RuntimeError
):
    def __init__(
        self,
        *,
        used_notional: Decimal,
        requested_notional: Decimal,
        max_daily_notional: Decimal,
    ) -> None:
        super().__init__(
            "live equity entry daily notional "
            "limit exceeded: "
            f"{used_notional} + "
            f"{requested_notional} > "
            f"{max_daily_notional}"
        )

        self.used_notional = (
            used_notional
        )

        self.requested_notional = (
            requested_notional
        )

        self.max_daily_notional = (
            max_daily_notional
        )


def _positive_decimal_argument(
    arguments: dict[str, str],
    *,
    field_name: str,
) -> Decimal:
    raw_value = arguments.get(
        field_name
    )

    if not isinstance(
        raw_value,
        str,
    ):
        raise ValueError(
            f"{field_name} is missing"
        )

    try:
        value = Decimal(
            raw_value
        )
    except InvalidOperation as exc:
        raise ValueError(
            f"{field_name} is invalid"
        ) from exc

    if (
        not value.is_finite()
        or value <= Decimal("0")
    ):
        raise ValueError(
            f"{field_name} must be "
            "positive and finite"
        )

    return value


def equity_entry_order_notional(
    plan: EquityEntryExecutionPlan,
) -> Decimal:
    if (
        plan.mode
        is EquityEntryExecutionMode
        .FRACTIONAL_MARKET
    ):
        if plan.dollar_amount is None:
            raise ValueError(
                "fractional market plan "
                "requires dollar_amount"
            )

        notional = plan.dollar_amount

    elif (
        plan.mode
        is EquityEntryExecutionMode
        .WHOLE_SHARE_LIMIT
    ):
        if (
            plan.quantity is None
            or plan.limit_price is None
        ):
            raise ValueError(
                "whole-share limit plan "
                "requires quantity and "
                "limit_price"
            )

        notional = (
            plan.quantity
            * plan.limit_price
        )

    else:
        raise ValueError(
            "unsupported equity entry "
            "execution mode"
        )

    if (
        not notional.is_finite()
        or notional <= Decimal("0")
    ):
        raise ValueError(
            "entry order notional must be "
            "positive and finite"
        )

    return notional


def equity_entry_placement_arguments_notional(
    arguments: dict[str, str],
) -> Decimal:
    order_type = arguments.get(
        "type"
    )

    if order_type == "market":
        return _positive_decimal_argument(
            arguments,
            field_name="dollar_amount",
        )

    if order_type == "limit":
        quantity = (
            _positive_decimal_argument(
                arguments,
                field_name="quantity",
            )
        )

        limit_price = (
            _positive_decimal_argument(
                arguments,
                field_name="limit_price",
            )
        )

        return (
            quantity
            * limit_price
        )

    raise ValueError(
        "unsupported equity entry "
        "placement arguments"
    )


def require_live_equity_entry_order_limit(
    plan: EquityEntryExecutionPlan,
    *,
    max_order_notional: Decimal = (
        MAX_LIVE_ENTRY_ORDER_NOTIONAL
    ),
) -> Decimal:
    if (
        not max_order_notional.is_finite()
        or max_order_notional
        <= Decimal("0")
    ):
        raise ValueError(
            "max_order_notional must be "
            "positive and finite"
        )

    notional = (
        equity_entry_order_notional(
            plan
        )
    )

    if notional > max_order_notional:
        raise (
            EquityEntryOrderLimitExceededError(
                "live equity entry order "
                "exceeds maximum notional: "
                f"{notional} > "
                f"{max_order_notional}"
            )
        )

    return notional