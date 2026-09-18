from stock_agent.execution import (
    ExecutionResult,
    ExitExecutionService,
)
from stock_agent.monitoring import PositionMonitorOutcome
from stock_agent.orchestration.execution_state import (
    apply_execution_result_to_position_state,
)
from stock_agent.orchestration.outcomes import (
    PositionExecutionOutcome,
)
from stock_agent.state import PositionStateStore


class ExecutionStateSyncError(
    RuntimeError
):
    def __init__(
        self,
        result: ExecutionResult,
        cause: Exception,
    ) -> None:
        super().__init__(
            "execution succeeded but position "
            "state synchronization failed"
        )
        self.result = result
        self.cause = cause


class ExitExecutionCoordinator:
    def __init__(
        self,
        execution_service: ExitExecutionService,
        state_store: PositionStateStore,
    ) -> None:
        self._execution_service = execution_service
        self._state_store = state_store

    def execute_outcome(
        self,
        outcome: PositionMonitorOutcome,
    ) -> ExecutionResult | None:
        if not outcome.succeeded:
            return None

        if outcome.exit_intent is None:
            return None

        result = self._execution_service.execute(
            outcome.exit_intent
        )

        if result is None:
            return None

        try:
            apply_execution_result_to_position_state(
                self._state_store,
                result,
            )
        except Exception as error:
            raise ExecutionStateSyncError(
                result,
                error,
            ) from error

        return result

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
            except ExecutionStateSyncError as error:
                execution_outcomes.append(
                    PositionExecutionOutcome(
                        position_id=(
                            outcome.position_id
                        ),
                        symbol=outcome.symbol,
                        result=error.result,
                        state_sync_error=(
                            error.cause
                        ),
                    )
                )
                continue
            except Exception as error:
                execution_outcomes.append(
                    PositionExecutionOutcome(
                        position_id=(
                            outcome.position_id
                        ),
                        symbol=outcome.symbol,
                        error=error,
                    )
                )
                continue

            execution_outcomes.append(
                PositionExecutionOutcome(
                    position_id=(
                        outcome.position_id
                    ),
                    symbol=outcome.symbol,
                    result=result,
                )
            )

        return execution_outcomes