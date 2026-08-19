from stock_agent.execution.intents import (
    ExitIntent,
    ExitReason,
)
from stock_agent.risk import (
    TrailingStopDecision,
    TrailingStopEvaluation,
)


def build_exit_intent(
    evaluation: TrailingStopEvaluation,
) -> ExitIntent | None:
    if evaluation.decision is not TrailingStopDecision.EXIT:
        return None

    state = evaluation.state

    return ExitIntent(
        position_id=state.position_id,
        account_number=state.account_number,
        asset_type=state.asset_type,
        symbol=state.symbol,
        quantity=state.remaining_quantity,
        reason=ExitReason.TRAILING_STOP,
        triggered_at=state.last_quote_at,
        option_id=state.option_id,
    )