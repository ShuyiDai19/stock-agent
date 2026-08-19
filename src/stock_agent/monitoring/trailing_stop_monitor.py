from stock_agent.market_data import QuoteProvider
from stock_agent.execution import build_exit_intent
from stock_agent.risk import (
    TrailingStopEvaluation,
    evaluate_trailing_stop,
)
from stock_agent.state import (
    PositionStateNotFoundError,
    PositionStateStatus,
    PositionStateStore,
)
from stock_agent.monitoring.outcomes import (
    PositionMonitorOutcome,
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

    def monitor_active_positions(
        self,
        *,
        account_number: str,
    ) -> list[PositionMonitorOutcome]:
        states = self._store.list_by_status(
            account_number=account_number,
            statuses=(PositionStateStatus.ACTIVE,),
        )

        outcomes: list[PositionMonitorOutcome] = []

        for state in states:
            try:
                evaluation = self.process_position(
                    state.position_id,
                )
            except Exception as error:
                outcomes.append(
                    PositionMonitorOutcome(
                        position_id=state.position_id,
                        symbol=state.symbol,
                        error=error,
                    )
                )
                continue

            exit_intent = build_exit_intent(
                evaluation,
            )

            outcomes.append(
                PositionMonitorOutcome(
                    position_id=state.position_id,
                    symbol=state.symbol,
                    evaluation=evaluation,
                    exit_intent=exit_intent,
                )
            )

        return outcomes