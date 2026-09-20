from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.orchestration.candidate_loading import (
    EquityCandidateLoadItem,
    EquityCandidateLoadOutcome,
    load_robinhood_equity_review_candidates,
)
from stock_agent.orchestration.entry_review_batch import (
    EntryReviewBatchItem,
)
from stock_agent.orchestration.strategy_cycle import (
    EquityStrategyCycleInput,
    EquityStrategyCycleOutcome,
    run_equity_strategy_cycle,
)
from stock_agent.risk.entry_portfolio import (
    OpenPositionRiskSnapshot,
)
from stock_agent.strategy.candidate_generation import (
    DEFAULT_ENTRY_BUDGET,
)
from stock_agent.orchestration.portfolio_state import (
    PositionRiskStateStore,
    load_open_position_risk_snapshots,
)
from enum import StrEnum

from stock_agent.strategy.market_session import (
    RegularMarketSession,
    XnysRegularMarketSessionResolver,
)


@dataclass(frozen=True, slots=True)
class RobinhoodEquityStrategyCycleOutcome:
    candidate_loading: EquityCandidateLoadOutcome
    strategy: EquityStrategyCycleOutcome

    @property
    def eligible_entries(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return (
            self.strategy
            .eligible_entries
        )

    @property
    def market_data_errors(
        self,
    ) -> tuple[
        EquityCandidateLoadItem,
        ...,
    ]:
        return (
            self.candidate_loading
            .errors
        )

    @property
    def review_errors(
        self,
    ) -> tuple[
        EntryReviewBatchItem,
        ...,
    ]:
        return (
            self.strategy
            .errors
        )

    @property
    def loaded_candidate_count(
        self,
    ) -> int:
        return (
            self.candidate_loading
            .candidate_count
        )

    @property
    def eligible_entry_count(
        self,
    ) -> int:
        return len(
            self.eligible_entries
        )

    @property
    def market_data_error_count(
        self,
    ) -> int:
        return len(
            self.market_data_errors
        )

    @property
    def review_error_count(
        self,
    ) -> int:
        return len(
            self.review_errors
        )

class RobinhoodEquityCycleRunStatus(
    StrEnum
):
    RAN = "ran"
    NO_TRADE = "no_trade"


@dataclass(
    frozen=True,
    slots=True,
)
class RobinhoodEquityCycleRunOutcome:
    status: (
        RobinhoodEquityCycleRunStatus
    )

    session: RegularMarketSession

    cycle: (
        RobinhoodEquityStrategyCycleOutcome
        | None
    )

    reason: str | None = None

    def __post_init__(
        self,
    ) -> None:
        if (
            self.status
            is RobinhoodEquityCycleRunStatus
            .RAN
        ):
            if self.cycle is None:
                raise ValueError(
                    "RAN outcome requires cycle"
                )

            return

        if self.cycle is not None:
            raise ValueError(
                "NO_TRADE outcome cannot "
                "contain cycle"
            )

    @property
    def eligible_entries(
        self,
    ):
        if self.cycle is None:
            return ()

        return (
            self.cycle
            .eligible_entries
        )

    @property
    def eligible_entry_count(
        self,
    ) -> int:
        return len(
            self.eligible_entries
        )

    @property
    def loaded_candidate_count(
        self,
    ) -> int:
        if self.cycle is None:
            return 0

        return (
            self.cycle
            .loaded_candidate_count
        )

    @property
    def market_data_error_count(
        self,
    ) -> int:
        if self.cycle is None:
            return 0

        return (
            self.cycle
            .market_data_error_count
        )

    @property
    def review_error_count(
        self,
    ) -> int:
        if self.cycle is None:
            return 0

        return (
            self.cycle
            .review_error_count
        )


def run_robinhood_equity_strategy_cycle(
    invoker: MCPToolInvoker,
    *,
    account_number: str,
    symbols: tuple[
        str,
        ...,
    ],
    open_positions: tuple[
        OpenPositionRiskSnapshot,
        ...,
    ],
    session_start: datetime,
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> RobinhoodEquityStrategyCycleOutcome:
    candidate_loading = (
        load_robinhood_equity_review_candidates(
            invoker,
            symbols=symbols,
            session_start=session_start,
            evaluated_at=evaluated_at,
            budget=budget,
        )
    )

    cycle_input = (
        EquityStrategyCycleInput(
            account_number=(
                account_number
            ),
            candidates=(
                candidate_loading
                .candidates
            ),
            open_positions=(
                open_positions
            ),
            evaluated_at=(
                evaluated_at
            ),
        )
    )

    strategy = (
        run_equity_strategy_cycle(
            invoker,
            cycle_input,
        )
    )

    return (
        RobinhoodEquityStrategyCycleOutcome(
            candidate_loading=(
                candidate_loading
            ),
            strategy=strategy,
        )
    )

def run_robinhood_equity_strategy_cycle_from_store(
    invoker: MCPToolInvoker,
    store: PositionRiskStateStore,
    *,
    account_number: str,
    symbols: tuple[
        str,
        ...,
    ],
    evaluated_at: datetime,
    budget: Decimal = DEFAULT_ENTRY_BUDGET,
) -> RobinhoodEquityCycleRunOutcome:
    resolver = (
        XnysRegularMarketSessionResolver()
    )

    session = resolver.resolve(
        evaluated_at
    )

    if not session.is_open:
        return (
            RobinhoodEquityCycleRunOutcome(
                status=(
                    RobinhoodEquityCycleRunStatus
                    .NO_TRADE
                ),
                session=session,
                cycle=None,
                reason=(
                    "regular market session "
                    f"is {session.status.value}"
                ),
            )
        )

    open_positions = (
        load_open_position_risk_snapshots(
            store,
            account_number=(
                account_number
            ),
        )
    )

    cycle = (
        run_robinhood_equity_strategy_cycle(
            invoker,
            account_number=(
                account_number
            ),
            symbols=symbols,
            open_positions=(
                open_positions
            ),
            session_start=(
                session.opens_at
            ),
            evaluated_at=(
                evaluated_at
            ),
            budget=budget,
        )
    )

    return (
        RobinhoodEquityCycleRunOutcome(
            status=(
                RobinhoodEquityCycleRunStatus
                .RAN
            ),
            session=session,
            cycle=cycle,
        )
    )