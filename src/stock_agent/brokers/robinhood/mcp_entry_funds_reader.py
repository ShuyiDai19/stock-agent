from decimal import (
    Decimal,
    InvalidOperation,
)
from typing import Any

from stock_agent.brokers.robinhood.entry_funds import (
    RobinhoodEntryFundsSnapshot,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)


def _parse_non_negative_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{field_name} must be numeric"
        )

    if not isinstance(
        value,
        (
            str,
            int,
            float,
            Decimal,
        ),
    ):
        raise ValueError(
            f"{field_name} must be numeric"
        )

    if isinstance(
        value,
        str,
    ):
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} must not "
                "be empty"
            )
    else:
        normalized = str(value)

    try:
        amount = Decimal(
            normalized
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field_name} must be "
            "a valid decimal"
        ) from exc

    if (
        not amount.is_finite()
        or amount < Decimal("0")
    ):
        raise ValueError(
            f"{field_name} must be "
            "finite and non-negative"
        )

    return amount


def decode_robinhood_entry_funds(
    raw_result: Any,
) -> RobinhoodEntryFundsSnapshot:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood portfolio result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood portfolio result "
            "must contain data"
        )

    currency = data.get(
        "currency"
    )

    if (
        not isinstance(
            currency,
            str,
        )
        or currency.strip().upper()
        != "USD"
    ):
        raise ValueError(
            "Robinhood portfolio currency "
            "must be USD"
        )

    cash = (
        _parse_non_negative_decimal(
            data.get(
                "cash"
            ),
            field_name="cash",
        )
    )

    buying_power_data = (
        data.get(
            "buying_power"
        )
    )

    if not isinstance(
        buying_power_data,
        dict,
    ):
        raise ValueError(
            "Robinhood portfolio "
            "buying_power must be "
            "a mapping"
        )

    display_currency = (
        buying_power_data.get(
            "display_currency"
        )
    )

    if (
        not isinstance(
            display_currency,
            str,
        )
        or display_currency
        .strip()
        .upper()
        != "USD"
    ):
        raise ValueError(
            "Robinhood buying power "
            "currency must be USD"
        )

    buying_power = (
        _parse_non_negative_decimal(
            buying_power_data.get(
                "unleveraged_buying_power"
            ),
            field_name=(
                "unleveraged_buying_power"
            ),
        )
    )

    return RobinhoodEntryFundsSnapshot(
        buying_power=buying_power,
        cash=cash,
    )


class MCPRobinhoodEntryFundsReader:
    def __init__(
        self,
        invoker: MCPToolInvoker,
    ) -> None:
        self._invoker = invoker

    def read(
        self,
        *,
        account_number: str,
    ) -> RobinhoodEntryFundsSnapshot:
        if not isinstance(
            account_number,
            str,
        ):
            raise TypeError(
                "account_number must "
                "be a string"
            )

        if not account_number.strip():
            raise ValueError(
                "account_number cannot "
                "be empty"
            )

        raw_result = (
            self._invoker.call_tool(
                "get_portfolio",
                {
                    "account_number":
                        account_number,
                },
            )
        )

        return (
            decode_robinhood_entry_funds(
                raw_result
            )
        )