from datetime import datetime
from stock_agent.brokers.robinhood.reconciliation import (
    PlacementReconciliationRequest,
)

class LiveExecutionDisabledError(RuntimeError):
    pass

class RobinhoodOrderReviewRejectedError(RuntimeError):
    pass

class RobinhoodOrderReviewMismatchError(RuntimeError):
    pass

class RobinhoodOrderNotReviewedError(RuntimeError):
    pass

class RobinhoodPlacementUncertainError(RuntimeError):
    def __init__(
        self,
        reconciliation_request: PlacementReconciliationRequest,
    ) -> None:
        super().__init__(
            "Robinhood order placement outcome is uncertain"
        )

        self.reconciliation_request = (
            reconciliation_request
        )

    @property
    def position_id(self) -> str:
        return self.reconciliation_request.position_id

    @property
    def ref_id(self) -> str:
        return self.reconciliation_request.ref_id

class RobinhoodAcknowledgementPersistenceError(
    RuntimeError
):
    def __init__(
        self,
        *,
        ref_id: str,
        broker_order_id: str,
        acknowledged_at: datetime,
    ) -> None:
        super().__init__(
            "Robinhood order was acknowledged but "
            "local acknowledgement persistence failed"
        )

        self.ref_id = ref_id
        self.broker_order_id = broker_order_id
        self.acknowledged_at = acknowledged_at