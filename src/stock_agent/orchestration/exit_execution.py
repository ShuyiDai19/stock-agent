from stock_agent.execution import (
    ExecutionResult,
    ExitExecutionService,
)
from stock_agent.monitoring import PositionMonitorOutcome
from stock_agent.orchestration.outcomes import (
    PositionExecutionOutcome,
)


class ExitExecutionCoordinator:
    def __init__(
        self,
        execution_service: ExitExecutionService,
    ) -> None:
        self._execution_service = execution_service

    def execute_outcome(
        self,
        outcome: PositionMonitorOutcome,
    ) -> ExecutionResult | None:
        if not outcome.succeeded:
            return None

        if outcome.exit_intent is None:
            return None

        return self._execution_service.execute(
            outcome.exit_intent
        )

    def execute_outcomes(
        self,
        outcomes: list[PositionMonitorOutcome],
    ) -> list[PositionExecutionOutcome]:
        execution_outcomes: list[
            PositionExecutionOutcome
        ] = []

        for outcome in outcomes:
            try:
                result = self.execute_outcome(
                    outcome
                )
            except Exception as error:
                execution_outcomes.append(
                    PositionExecutionOutcome(
                        position_id=outcome.position_id,
                        symbol=outcome.symbol,
                        error=error,
                    )
                )
                continue

            execution_outcomes.append(
                PositionExecutionOutcome(
                    position_id=outcome.position_id,
                    symbol=outcome.symbol,
                    result=result,
                )
            )

        return execution_outcomes