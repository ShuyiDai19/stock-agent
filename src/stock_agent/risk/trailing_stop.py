from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum

from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)


class TrailingStopDecision(str, Enum):
    HOLD = "hold"
    EXIT = "exit"


@dataclass(frozen=True)
class TrailingStopEvaluation:
    state: PositionRuntimeState
    decision: TrailingStopDecision
    reason: str


def evaluate_trailing_stop(
    state: PositionRuntimeState,
    *,
    latest_bid: Decimal,
    observed_at: datetime,
) -> TrailingStopEvaluation:
    """Evaluate one executable bid against the position's trailing state."""

    if latest_bid <= 0:
        raise ValueError("latest_bid must be greater than zero")

    if state.status is not PositionStateStatus.ACTIVE:
        raise ValueError("trailing stop can only evaluate an active position")

    highest_bid = max(
        state.highest_executable_bid,
        latest_bid,
    )

    activation_price = (
        state.entry_price
        * (Decimal("1") + state.activation_gain_ratio)
    )

    should_arm = (
        not state.trailing_armed
        and latest_bid >= activation_price
    )

    updated_state = replace(
        state,
        highest_executable_bid=highest_bid,
        trailing_armed=(
            True if should_arm else state.trailing_armed
        ),
        trailing_armed_at=(
            observed_at
            if should_arm
            else state.trailing_armed_at
        ),
        last_quote_at=observed_at,
        version=state.version + 1,
    )

    exit_threshold = (
        highest_bid
        * (Decimal("1") - state.drawdown_ratio)
    )

    should_exit = (
        updated_state.trailing_armed
        and latest_bid <= exit_threshold
    )

    if should_exit:
        return TrailingStopEvaluation(
            state=updated_state,
            decision=TrailingStopDecision.EXIT,
            reason="trailing stop triggered",
        )

    return TrailingStopEvaluation(
        state=updated_state,
        decision=TrailingStopDecision.HOLD,
        reason=(
            "trailing stop armed"
            if should_arm
            else "trailing stop conditions were not met"
        ),
    )