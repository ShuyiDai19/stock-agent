from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodEntryFundsSnapshot:
    buying_power: Decimal
    cash: Decimal

    def __post_init__(self) -> None:
        if (
            not self.buying_power.is_finite()
            or self.buying_power
            < Decimal("0")
        ):
            raise ValueError(
                "buying_power must be "
                "finite and non-negative"
            )

        if (
            not self.cash.is_finite()
            or self.cash
            < Decimal("0")
        ):
            raise ValueError(
                "cash must be finite "
                "and non-negative"
            )


class RobinhoodEntryFundsReader(
    Protocol
):
    def read(
        self,
        *,
        account_number: str,
    ) -> RobinhoodEntryFundsSnapshot:
        ...