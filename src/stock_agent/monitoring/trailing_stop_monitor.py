from stock_agent.domain import QuoteSnapshot
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
        quote: QuoteSnapshot,
    ) -> TrailingStopEvaluation:
        state = self._store.get(position_id)

        if state is None:
            raise PositionStateNotFoundError(
                f"position state not found: {position_id}"
            )

        if quote.symbol != state.symbol:
            raise ValueError(
                "quote symbol does not match position symbol"
            )

        result = evaluate_trailing_stop(
            state,
            latest_bid=quote.bid,
            observed_at=quote.observed_at,
        )

        self._store.update(
            result.state,
            expected_version=state.version,
        )

        return result