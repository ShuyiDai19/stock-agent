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