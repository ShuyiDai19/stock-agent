from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
)
import logging
from dataclasses import (
    dataclass,
    field,
)
from pathlib import Path

from stock_agent.brokers.robinhood.config import (
    parse_live_execution_enabled,
)
from stock_agent.brokers.robinhood.connection import (
    open_robinhood_mcp_invoker,
)
from stock_agent.brokers.robinhood.guarded_client import (
    GuardedRobinhoodBrokerClient,
)
from stock_agent.brokers.robinhood.mcp_client import (
    MCPRobinhoodBrokerClient,
)
from stock_agent.brokers.robinhood.mcp_receipt_decoder import (
    RobinhoodMCPReceiptDecoder,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptJournal,
    SQLitePlacementAttemptJournal,
)
from stock_agent.brokers.robinhood.mcp_order_lookup import (
    MCPRobinhoodOrderLookup,
)
from stock_agent.brokers.robinhood.placement_recovery import (
    PlacementRecoveryPlanner,
)
from stock_agent.brokers.robinhood.placement_recovery_service import (
    PlacementRecoveryResult,
    PlacementRecoveryService,
)
from stock_agent.brokers.robinhood.reconciler import (
    RobinhoodPlacementReconciler,
)
from stock_agent.brokers.robinhood.entry_activation_reconciler import (
    RobinhoodEquityEntryActivationReconciler,
)
if TYPE_CHECKING:
    from stock_agent.brokers.robinhood.entry_placer import (
        RobinhoodApprovedEquityEntryPlacer,
    )
    from stock_agent.brokers.robinhood.entry_preflight_reader import (
        RobinhoodEquityEntryPreflightReader,
    )
from stock_agent.brokers.robinhood.entry_placement import (
    SQLiteEquityEntryPlacementJournal,
)
from stock_agent.brokers.robinhood.entry_placement_recovery import (
    EquityEntryPlacementRecoveryService,
)
from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
)
from stock_agent.state import (
    SQLitePositionStateStore,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)


ROBINHOOD_LIVE_EXECUTION_ENV = (
    "ROBINHOOD_LIVE_EXECUTION_ENABLED"
)
STOCK_AGENT_RUNTIME_MODE_ENV = (
    "STOCK_AGENT_RUNTIME_MODE"
)
ROBINHOOD_PLACEMENT_JOURNAL_PATH_ENV = (
    "ROBINHOOD_PLACEMENT_JOURNAL_PATH"
)
DEFAULT_ROBINHOOD_PLACEMENT_JOURNAL_PATH = Path(
    ".state/robinhood/placement.sqlite3"
)
ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH_ENV = (
    "ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH"
)

DEFAULT_ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH = Path(
    ".state/robinhood/entry-placement.sqlite3"
)

ROBINHOOD_POSITION_STATE_PATH_ENV = (
    "ROBINHOOD_POSITION_STATE_PATH"
)

DEFAULT_ROBINHOOD_POSITION_STATE_PATH = Path(
    ".state/robinhood/positions.sqlite3"
)

logger = logging.getLogger(__name__)
def resolve_runtime_mode(
    env: Mapping[str, str] | None = None,
) -> str:
    source = os.environ if env is None else env

    raw_runtime_mode = source.get(
        STOCK_AGENT_RUNTIME_MODE_ENV
    )

    if raw_runtime_mode is None:
        return "safe"

    runtime_mode = (
        raw_runtime_mode
        .strip()
        .lower()
    )

    if runtime_mode not in {
        "safe",
        "live",
    }:
        raise ValueError(
            "STOCK_AGENT_RUNTIME_MODE must "
            "be either 'safe' or 'live'"
        )

    return runtime_mode


def resolve_live_execution_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    source = os.environ if env is None else env

    live_enabled = parse_live_execution_enabled(
        source.get(
            ROBINHOOD_LIVE_EXECUTION_ENV
        )
    )

    runtime_mode = resolve_runtime_mode(
        source
    )

    return (
        live_enabled
        and runtime_mode == "live"
    )

def resolve_placement_journal_path(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> Path:
    source = os.environ if env is None else env

    raw_path = source.get(
        ROBINHOOD_PLACEMENT_JOURNAL_PATH_ENV
    )

    if raw_path is None:
        path = (
            DEFAULT_ROBINHOOD_PLACEMENT_JOURNAL_PATH
        )
    else:
        stripped = raw_path.strip()

        if not stripped:
            raise ValueError(
                "ROBINHOOD_PLACEMENT_JOURNAL_PATH "
                "must not be empty"
            )

        path = Path(stripped)

    if path.is_absolute():
        return path

    root = (
        Path.cwd()
        if base_dir is None
        else base_dir
    )

    return root / path

def resolve_entry_placement_journal_path(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> Path:
    source = os.environ if env is None else env

    raw_path = source.get(
        ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH_ENV
    )

    if raw_path is None:
        path = (
            DEFAULT_ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH
        )
    else:
        stripped = raw_path.strip()

        if not stripped:
            raise ValueError(
                "ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH "
                "must not be empty"
            )

        path = Path(stripped)

    if path.is_absolute():
        return path

    root = (
        Path.cwd()
        if base_dir is None
        else base_dir
    )

    return root / path

def resolve_position_state_path(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> Path:
    source = os.environ if env is None else env

    raw_path = source.get(
        ROBINHOOD_POSITION_STATE_PATH_ENV
    )

    if raw_path is None:
        path = (
            DEFAULT_ROBINHOOD_POSITION_STATE_PATH
        )
    else:
        stripped = raw_path.strip()

        if not stripped:
            raise ValueError(
                "ROBINHOOD_POSITION_STATE_PATH "
                "must not be empty"
            )

        path = Path(stripped)

    if path.is_absolute():
        return path

    root = (
        Path.cwd()
        if base_dir is None
        else base_dir
    )

    return root / path

def build_production_entry_placement_journal(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> SQLiteEquityEntryPlacementJournal:
    path = resolve_entry_placement_journal_path(
        env,
        base_dir=base_dir,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    journal = SQLiteEquityEntryPlacementJournal(
        path
    )

    journal.initialize()

    return journal

def build_production_position_state_store(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> SQLitePositionStateStore:
    path = resolve_position_state_path(
        env,
        base_dir=base_dir,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    store = SQLitePositionStateStore(
        path
    )

    store.initialize()

    return store

def build_production_placement_journal(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> SQLitePlacementAttemptJournal:
    path = resolve_placement_journal_path(
        env,
        base_dir=base_dir,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    journal = SQLitePlacementAttemptJournal(
        path
    )

    journal.initialize()

    return journal

def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _build_guarded_robinhood_broker(
    *,
    invoker: Any,
    placement_journal: PlacementAttemptJournal,
    live_enabled: bool,
) -> GuardedRobinhoodBrokerClient:
    broker = MCPRobinhoodBrokerClient(
        invoker=invoker,
        receipt_decoder=(
            RobinhoodMCPReceiptDecoder(
                clock=_utc_now
            )
        ),
        placement_clock=_utc_now,
        placement_journal=placement_journal,
    )

    return GuardedRobinhoodBrokerClient(
        broker,
        live_enabled=live_enabled,
    )


@contextmanager
def open_robinhood_broker(
    *,
    account_number: str,
    placement_journal: PlacementAttemptJournal,
    live_enabled: bool = False,
    client_factory: Callable[[Any], Any] | None = None,
    startup_timeout_seconds: float = 10.0,
    call_timeout_seconds: float = 30.0,
    shutdown_timeout_seconds: float = 10.0,
) -> Iterator[GuardedRobinhoodBrokerClient]:
    if not isinstance(
        live_enabled,
        bool,
    ):
        raise TypeError(
            "live_enabled must be a bool"
        )

    with open_robinhood_mcp_invoker(
        allowed_account_number=account_number,
        client_factory=client_factory,
        startup_timeout_seconds=(
            startup_timeout_seconds
        ),
        call_timeout_seconds=(
            call_timeout_seconds
        ),
        shutdown_timeout_seconds=(
            shutdown_timeout_seconds
        ),
    ) as invoker:
        yield _build_guarded_robinhood_broker(
            invoker=invoker,
            placement_journal=placement_journal,
            live_enabled=live_enabled,
        )

@contextmanager
def open_robinhood_broker_from_env(
    *,
    account_number: str,
    placement_journal: PlacementAttemptJournal,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[[Any], Any] | None = None,
    startup_timeout_seconds: float = 10.0,
    call_timeout_seconds: float = 30.0,
    shutdown_timeout_seconds: float = 10.0,
) -> Iterator[GuardedRobinhoodBrokerClient]:

    summary = build_startup_safety_summary(
        env
    )

    logger.warning(
        format_startup_safety_summary(
            summary
        )
    )

    live_enabled = (
        summary.live_execution_enabled
    )

    with open_robinhood_broker(
        account_number=account_number,
        placement_journal=placement_journal,
        live_enabled=live_enabled,
        client_factory=client_factory,
        startup_timeout_seconds=(
            startup_timeout_seconds
        ),
        call_timeout_seconds=(
            call_timeout_seconds
        ),
        shutdown_timeout_seconds=(
            shutdown_timeout_seconds
        ),
    ) as broker:
        yield broker

@dataclass(frozen=True)
class RobinhoodStartupSafetySummary:
    runtime_mode: str
    live_execution_enabled: bool
    account_guard_enabled: bool

@dataclass(frozen=True)
class RobinhoodStartupRecoverySummary:
    results: tuple[
        PlacementRecoveryResult,
        ...
    ]
    unresolved_attempt_count: int

    @property
    def has_unresolved_attempts(
        self,
    ) -> bool:
        return (
            self.unresolved_attempt_count > 0
        )

@dataclass(frozen=True)
class RobinhoodRuntimeSession:
    account_number: str

    broker: GuardedRobinhoodBrokerClient

    _strategy_invoker: MCPToolInvoker = field(
        repr=False,
        compare=False,
    )

    # Exit lifecycle.
    placement_journal: PlacementAttemptJournal
    recovery: RobinhoodStartupRecoverySummary
    equity_exit_reconciler: (
        RobinhoodEquityExitReconciler
    )

    # Entry lifecycle.
    entry_placement_journal: (
        SQLiteEquityEntryPlacementJournal
    )
    position_store: SQLitePositionStateStore
    entry_recovery_service: (
        EquityEntryPlacementRecoveryService
    )
    entry_activation_reconciler: (
        RobinhoodEquityEntryActivationReconciler
    )
    entry_preflight_reader: (
        RobinhoodEquityEntryPreflightReader
    )
    entry_placer: (
        RobinhoodApprovedEquityEntryPlacer
        | None
    )
    

    live_execution_requested: bool
    live_execution_enabled: bool

    def __post_init__(self) -> None:
        if not self.account_number.strip():
            raise ValueError(
                "account_number cannot be empty"
            )

        if (
            self.live_execution_enabled
            and not self.live_execution_requested
        ):
            raise ValueError(
                "live execution cannot be enabled "
                "unless it was requested"
            )

        if (
            self.live_execution_enabled
            and self.entry_placer is None
        ):
            raise ValueError(
                "live runtime requires entry placer"
            )

        if (
            not self.live_execution_enabled
            and self.entry_placer is not None
        ):
            raise ValueError(
                "non-live runtime cannot expose "
                "entry placer"
            )

        if (
            self.live_execution_enabled
            and self.entry_preflight_reader is None
        ):
            raise ValueError(
                "live runtime requires "
                "entry preflight reader"
            )

def run_robinhood_startup_recovery(
    *,
    invoker: Any,
    placement_journal: PlacementAttemptJournal,
    not_found_grace_period: timedelta,
) -> RobinhoodStartupRecoverySummary:
    lookup = MCPRobinhoodOrderLookup(
        invoker
    )

    reconciler = RobinhoodPlacementReconciler(
        lookup,
        clock=_utc_now,
        not_found_grace_period=(
            not_found_grace_period
        ),
    )

    recovery_service = PlacementRecoveryService(
        placement_journal,
        PlacementRecoveryPlanner(),
        reconciler,
    )

    results = tuple(
        recovery_service.recover()
    )

    unresolved = (
        placement_journal.list_unresolved()
    )

    return RobinhoodStartupRecoverySummary(
        results=results,
        unresolved_attempt_count=len(
            unresolved
        ),
    )

@contextmanager
def open_robinhood_runtime(
    *,
    account_number: str,
    not_found_grace_period: timedelta,
    env: Mapping[str, str] | None = None,
    placement_journal: (
        PlacementAttemptJournal | None
    ) = None,
    entry_placement_journal: (
        SQLiteEquityEntryPlacementJournal
        | None
    ) = None,
    position_store: (
        SQLitePositionStateStore
        | None
    ) = None,
    base_dir: Path | None = None,
    client_factory: Callable[[Any], Any] | None = None,
    startup_timeout_seconds: float = 10.0,
    call_timeout_seconds: float = 30.0,
    shutdown_timeout_seconds: float = 10.0,
) -> Iterator[RobinhoodRuntimeSession]:
    safety_summary = (
        build_startup_safety_summary(
            env
        )
    )

    logger.warning(
        format_startup_safety_summary(
            safety_summary
        )
    )

    journal = placement_journal

    if journal is None:
        journal = (
            build_production_placement_journal(
                env,
                base_dir=base_dir,
            )
        )

    entry_journal = (
        entry_placement_journal
    )

    if entry_journal is None:
        entry_journal = (
            build_production_entry_placement_journal(
                env,
                base_dir=base_dir,
            )
        )

    runtime_position_store = (
        position_store
    )

    if runtime_position_store is None:
        runtime_position_store = (
            build_production_position_state_store(
                env,
                base_dir=base_dir,
            )
        )

    with open_robinhood_mcp_invoker(
        allowed_account_number=account_number,
        client_factory=client_factory,
        startup_timeout_seconds=(
            startup_timeout_seconds
        ),
        call_timeout_seconds=(
            call_timeout_seconds
        ),
        shutdown_timeout_seconds=(
            shutdown_timeout_seconds
        ),
    ) as invoker:
        recovery = (
            run_robinhood_startup_recovery(
                invoker=invoker,
                placement_journal=journal,
                not_found_grace_period=(
                    not_found_grace_period
                ),
            )
        )

        live_requested = (
            safety_summary.live_execution_enabled
        )

        live_enabled = (
            live_requested
            and not recovery.has_unresolved_attempts
        )

        from stock_agent.brokers.robinhood.exit_state_reconciliation import (
            EquityExitStateReconciler,
        )
        from stock_agent.brokers.robinhood.equity_exit_reconciler import (
            RobinhoodEquityExitReconciler,
        )
        from stock_agent.brokers.robinhood.journal_position_close_service import (
            JournalBackedEquityPositionCloseService,
        )
        from stock_agent.brokers.robinhood.mcp_order_execution_reader import (
            MCPRobinhoodEquityOrderExecutionReader,
        )
        from stock_agent.brokers.robinhood.position_close_service import (
            EquityPositionCloseConfirmationService,
        )

        exit_state_reconciler = (
            EquityExitStateReconciler(
                journal,
                runtime_position_store,
            )
        )

        exit_execution_reader = (
            MCPRobinhoodEquityOrderExecutionReader(
                invoker
            )
        )

        exit_close_confirmation_service = (
            EquityPositionCloseConfirmationService(
                runtime_position_store,
                exit_execution_reader,
                clock=_utc_now,
            )
        )

        exit_close_service = (
            JournalBackedEquityPositionCloseService(
                journal,
                exit_close_confirmation_service,
            )
        )

        equity_exit_reconciler = (
            RobinhoodEquityExitReconciler(
                exit_state_reconciler,
                exit_close_service,
                runtime_position_store,
            )
        )

        entry_lookup = (
            MCPRobinhoodOrderLookup(
                invoker
            )
        )

        entry_recovery_service = (
            EquityEntryPlacementRecoveryService(
                entry_journal,
                entry_lookup,
                clock=_utc_now,
            )
        )

        entry_quote_provider = (
            MCPRobinhoodEquityQuoteProvider(
                invoker
            )
        )

        entry_activation_reconciler = (
            RobinhoodEquityEntryActivationReconciler(
                invoker,
                entry_journal,
                runtime_position_store,
                entry_quote_provider,
            )
        )

        from stock_agent.brokers.robinhood.position_reader import (
            MCPRobinhoodEquityPositionReader,
        )
        from stock_agent.brokers.robinhood.option_exposure_reader import (
            MCPRobinhoodOptionExposureReader,
        )
        from stock_agent.brokers.robinhood.mcp_order_activity_reader import (
            MCPRobinhoodOrderActivityReader,
        )
        from stock_agent.brokers.robinhood.mcp_entry_funds_reader import (
            MCPRobinhoodEntryFundsReader,
        )
        from stock_agent.brokers.robinhood.entry_preflight_reader import (
            RobinhoodEquityEntryPreflightReader,
        )

        entry_preflight_reader = (
            RobinhoodEquityEntryPreflightReader(
                position_reader=(
                    MCPRobinhoodEquityPositionReader(
                        invoker
                    )
                ),
                option_exposure_reader=(
                    MCPRobinhoodOptionExposureReader(
                        invoker
                    )
                ),
                order_activity_reader=(
                    MCPRobinhoodOrderActivityReader(
                        invoker
                    )
                ),
                funds_reader=(
                    MCPRobinhoodEntryFundsReader(
                        invoker
                    )
                ),
            )
        )

        entry_placer = None

        if live_enabled:
            from stock_agent.brokers.robinhood.entry_placer import (
                RobinhoodApprovedEquityEntryPlacer,
            )

            entry_placer = (
                RobinhoodApprovedEquityEntryPlacer(
                    invoker,
                    entry_journal,
                    clock=_utc_now,
                )
            )

        if (
            live_requested
            and not live_enabled
        ):
            logger.warning(
                "Robinhood live execution "
                "BLOCKED: unresolved placement "
                "attempts=%d",
                recovery.unresolved_attempt_count,
            )
            

        broker = (
            _build_guarded_robinhood_broker(
                invoker=invoker,
                placement_journal=journal,
                live_enabled=live_enabled,
            )
        )

        yield RobinhoodRuntimeSession(
            account_number=account_number,
            broker=broker,
            _strategy_invoker=invoker,
            placement_journal=journal,
            recovery=recovery,
            equity_exit_reconciler=(
                equity_exit_reconciler
            ),
            entry_placement_journal=(
                entry_journal
            ),
            position_store=(
                runtime_position_store
            ),
            entry_recovery_service=(
                entry_recovery_service
            ),
            entry_activation_reconciler=(
                entry_activation_reconciler
            ),
            entry_preflight_reader=(
                entry_preflight_reader
            ),
            entry_placer=entry_placer,
            live_execution_requested=(
                live_requested
            ),
            live_execution_enabled=(
                live_enabled
            ),
        )

def build_startup_safety_summary(
    env: Mapping[str, str] | None = None,
) -> RobinhoodStartupSafetySummary:
    return RobinhoodStartupSafetySummary(
        runtime_mode=resolve_runtime_mode(
            env
        ),
        live_execution_enabled=(
            resolve_live_execution_enabled(
                env
            )
        ),
        account_guard_enabled=True,
    )

def format_startup_safety_summary(
    summary: RobinhoodStartupSafetySummary,
) -> str:
    live_status = (
        "ENABLED"
        if summary.live_execution_enabled
        else "DISABLED"
    )

    guard_status = (
        "ENABLED"
        if summary.account_guard_enabled
        else "DISABLED"
    )

    return (
        "Robinhood startup safety: "
        f"runtime_mode={summary.runtime_mode} "
        f"live_execution={live_status} "
        f"account_guard={guard_status}"
    )