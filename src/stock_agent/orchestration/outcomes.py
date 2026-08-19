from dataclasses import dataclass

from stock_agent.execution import ExecutionResult


@dataclass(frozen=True)
class PositionExecutionOutcome:
    position_id: str
    symbol: str
    result: ExecutionResult | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        if self.result is not None and self.error is not None:
            raise ValueError(
                "execution outcome cannot contain both result and error"
            )

    @property
    def attempted(self) -> bool:
        return self.result is not None or self.error is not None

    @property
    def failed(self) -> bool:
        return self.error is not None