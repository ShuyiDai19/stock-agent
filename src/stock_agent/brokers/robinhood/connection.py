from contextlib import contextmanager
from typing import Any, Callable, Iterator

from stock_agent.brokers.robinhood.account_guard import (
    RobinhoodAccountGuardedMCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.oauth_client import (
    ROBINHOOD_MCP_URL,
    RobinhoodOAuthClientFactory,
)
from stock_agent.brokers.robinhood.persistent_mcp_invoker import (
    PersistentMCPToolInvoker,
)


@contextmanager
def open_robinhood_mcp_invoker(
    *,
    allowed_account_number: str,
    client_factory: Callable[[Any], Any] | None = None,
    startup_timeout_seconds: float = 10.0,
    call_timeout_seconds: float = 30.0,
    shutdown_timeout_seconds: float = 10.0,
) -> Iterator[MCPToolInvoker]:
    if not isinstance(
        allowed_account_number,
        str,
    ):
        raise TypeError(
            "allowed_account_number must be a string"
        )

    if not allowed_account_number.strip():
        raise ValueError(
            "allowed_account_number cannot be empty"
        )

    if client_factory is None:
        client_factory = (
            RobinhoodOAuthClientFactory()
        )

    transport = PersistentMCPToolInvoker(
        ROBINHOOD_MCP_URL,
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
    )

    guarded_invoker = (
        RobinhoodAccountGuardedMCPToolInvoker(
            transport,
            allowed_account_number=(
                allowed_account_number
            ),
        )
    )

    with transport:
        yield guarded_invoker