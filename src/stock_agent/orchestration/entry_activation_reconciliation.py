from typing import Protocol

from stock_agent.state import (
    PositionRuntimeState,
)


class EquityEntryActivationReconciler(
    Protocol
):
    def reconcile(
        self,
        *,
        account_number: str,
    ) -> tuple[
        PositionRuntimeState,
        ...,
    ]:
        ...