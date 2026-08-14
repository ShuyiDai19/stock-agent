from stock_agent.market_data import QuoteProvider
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
        quote_provider: QuoteProvider,
    ) -> None:
        self._store = store
        self._quote_provider = quote_provider

    def process_position(
        self,
        position_id: str,
    ) -> TrailingStopEvaluation:
        state = self._store.get(position_id)

        if state is None:
            raise PositionStateNotFoundError(
                f"position state not found: {position_id}"
            )

        quote = self._quote_provider.get_quote(
            state.symbol
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