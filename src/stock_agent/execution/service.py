from stock_agent.execution.executor import ExitExecutor
from stock_agent.execution.intents import ExitIntent
from stock_agent.execution.results import ExecutionResult


class ExitExecutionService:
    def __init__(
        self,
        executor: ExitExecutor,
    ) -> None:
        self._executor = executor

    def execute(
        self,
        intent: ExitIntent | None,
    ) -> ExecutionResult | None:
        if intent is None:
            return None

        return self._executor.execute(intent)