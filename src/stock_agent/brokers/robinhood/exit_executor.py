from collections.abc import Callable
from datetime import datetime, timezone

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitOrderRequest,
    build_robinhood_exit_order_request,
)
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExitIntent,
)


class DryRunRobinhoodExitExecutor:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )
        self.last_request: RobinhoodExitOrderRequest | None = None

    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        request = build_robinhood_exit_order_request(
            intent
        )

        self.last_request = request

        return ExecutionResult(
            position_id=intent.position_id,
            status=ExecutionStatus.PREVIEWED,
            submitted_at=self._clock(),
            broker_order_id=None,
            message="Robinhood exit order previewed; no order submitted",
        )