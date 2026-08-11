from datetime import datetime
from decimal import Decimal

from stock_agent.risk import (
    TrailingStopEvaluation,
    evaluate_trailing_stop,
)
from stock_agent.state import (
    PositionStateNotFoundError,
    PositionStateStore,
)


class TrailingStopMonitor:
    def __init__(
        self,
        store: PositionStateStore,
    ) -> None:
        self._store = store

    def process_quote(
        self,
        position_id: str,
        *,
        latest_bid: Decimal,
        observed_at: datetime,
    ) -> TrailingStopEvaluation:
        state = self._store.get(position_id)

        if state is None:
            raise PositionStateNotFoundError(
                f"position state not found: {position_id}"
            )

        result = evaluate_trailing_stop(
            state,
            latest_bid=latest_bid,
            observed_at=observed_at,
        )

        self._store.update(
            result.state,
            expected_version=state.version,
        )

        return result