from stock_agent.brokers.robinhood.entry_fill import (
    EquityEntryQuoteProvider,
    activate_acknowledged_equity_entries,
)
from stock_agent.brokers.robinhood.entry_placement import (
    SQLiteEquityEntryPlacementJournal,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStore,
)


class RobinhoodEquityEntryActivationReconciler:
    def __init__(
        self,
        invoker: MCPToolInvoker,
        journal: SQLiteEquityEntryPlacementJournal,
        store: PositionStateStore,
        quote_provider: EquityEntryQuoteProvider,
    ) -> None:
        self._invoker = invoker
        self._journal = journal
        self._store = store
        self._quote_provider = (
            quote_provider
        )

    def reconcile(
        self,
        *,
        account_number: str,
    ):
        if not account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        activated = tuple(
            activate_acknowledged_equity_entries(
                self._invoker,
                self._journal,
                self._store,
                self._quote_provider,
                account_number=account_number,
            )
        )

        remaining_acknowledged = (
            self._journal.list_acknowledged(
                account_number=account_number
            )
        )

        if remaining_acknowledged:
            raise RuntimeError(
                "entry activation reconciliation "
                "left acknowledged orders unresolved"
            )

        return activated