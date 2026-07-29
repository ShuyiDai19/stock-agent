from typing import Protocol

from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


class StateStoreError(RuntimeError):
    """Base error for persistent position-state operations."""


class PositionStateAlreadyExistsError(StateStoreError):
    """Raised when inserting an existing position state."""


class PositionStateNotFoundError(StateStoreError):
    """Raised when updating a position state that does not exist."""


class ConcurrentStateUpdateError(StateStoreError):
    """Raised when optimistic version checking detects a stale update."""


class PositionStateStore(Protocol):
    def initialize(self) -> None:
        """Create any required storage structures."""

    def insert(self, state: PositionRuntimeState) -> None:
        """Persist a newly discovered position."""

    def get(
        self,
        position_id: str,
    ) -> PositionRuntimeState | None:
        """Return one position state, or None when it does not exist."""

    def list_by_status(
        self,
        *,
        account_number: str,
        statuses: tuple[PositionStateStatus, ...],
    ) -> list[PositionRuntimeState]:
        """Return position states matching the requested statuses."""

    def update(
        self,
        state: PositionRuntimeState,
        *,
        expected_version: int,
    ) -> None:
        """
        Update an existing state using optimistic concurrency control.

        The update must fail when the stored version does not equal
        expected_version.
        """
