from typing import Protocol

from stock_agent.execution.intents import ExitIntent
from stock_agent.execution.results import ExecutionResult


class ExitExecutor(Protocol):
    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        ...