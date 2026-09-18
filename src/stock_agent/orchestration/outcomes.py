from dataclasses import dataclass

from stock_agent.execution import ExecutionResult

from dataclasses import dataclass

from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)


@dataclass(frozen=True)
class PositionExecutionOutcome:
    position_id: str
    symbol: str
    result: ExecutionResult | None = None
    error: Exception | None = None
    state_sync_error: Exception | None = None

    def __post_init__(self) -> None:
        if self.result is not None and self.error is not None:
            raise ValueError(
                "execution outcome cannot contain "
                "both result and error"
            )

        if (
            self.state_sync_error is not None
            and self.result is None
        ):
            raise ValueError(
                "state_sync_error requires "
                "an execution result"
            )

        if (
            self.state_sync_error is not None
            and self.result.status
            is not ExecutionStatus.SUBMITTED
        ):
            raise ValueError(
                "state_sync_error requires "
                "a submitted execution result"
            )

    @property
    def attempted(self) -> bool:
        return (
            self.result is not None
            or self.error is not None
        )

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def state_sync_failed(self) -> bool:
        return self.state_sync_error is not None