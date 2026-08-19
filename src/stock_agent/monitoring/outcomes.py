from dataclasses import dataclass

from stock_agent.execution import ExitIntent
from stock_agent.risk import TrailingStopEvaluation


@dataclass(frozen=True)
class PositionMonitorOutcome:
    position_id: str
    symbol: str
    evaluation: TrailingStopEvaluation | None = None
    exit_intent: ExitIntent | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        has_evaluation = self.evaluation is not None
        has_error = self.error is not None

        if has_evaluation == has_error:
            raise ValueError(
                "exactly one of evaluation or error must be set"
            )

        if self.error is not None and self.exit_intent is not None:
            raise ValueError(
                "failed outcome cannot contain an exit intent"
            )

    @property
    def succeeded(self) -> bool:
        return self.error is None