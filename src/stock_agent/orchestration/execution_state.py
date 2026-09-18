from dataclasses import replace

from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateNotFoundError,
    PositionStateStatus,
    PositionStateStore,
)


class ExecutionStateTransitionError(
    RuntimeError
):
    pass


def apply_execution_result_to_position_state(
    store: PositionStateStore,
    result: ExecutionResult,
) -> PositionRuntimeState | None:
    if result.status is not ExecutionStatus.SUBMITTED:
        return None

    state = store.get(
        result.position_id
    )

    if state is None:
        raise PositionStateNotFoundError(
            "position state not found: "
            f"{result.position_id}"
        )

    if state.status is PositionStateStatus.CLOSING:
        # Idempotent retry: the submitted exit has
        # already been reflected locally.
        return state

    if state.status is not PositionStateStatus.ACTIVE:
        raise ExecutionStateTransitionError(
            "submitted exit order cannot transition "
            f"position from {state.status.value!r} "
            "to closing"
        )

    updated_state = replace(
        state,
        status=PositionStateStatus.CLOSING,
        version=state.version + 1,
    )

    store.update(
        updated_state,
        expected_version=state.version,
    )

    return updated_state