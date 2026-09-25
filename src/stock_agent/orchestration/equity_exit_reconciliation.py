from typing import Protocol

from stock_agent.state.models import (
    PositionRuntimeState,
)


class EquityExitReconciler(
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