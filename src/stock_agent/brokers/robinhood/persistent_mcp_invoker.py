import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Event, Thread
from typing import Any, Callable

from mcp import Client

from stock_agent.brokers.robinhood.mcp import (
    MCPToolExecutionError,
    MCPToolInvocationNotSentError,
    MCPToolInvocationUncertainError,
    MCPToolResultShapeError,
    normalize_mcp_tool_result,
)


class PersistentMCPToolInvoker:
    def __init__(
        self,
        server: Any,
        *,
        client_factory: Callable[[Any], Any] = Client,
        startup_timeout_seconds: float = 10.0,
        call_timeout_seconds: float = 30.0,
        shutdown_timeout_seconds: float = 10.0,
    ) -> None:
        if startup_timeout_seconds <= 0:
            raise ValueError(
                "startup_timeout_seconds must be positive"
            )

        if call_timeout_seconds <= 0:
            raise ValueError(
                "call_timeout_seconds must be positive"
            )

        if shutdown_timeout_seconds <= 0:
            raise ValueError(
                "shutdown_timeout_seconds must be positive"
            )

        self._server = server
        self._client_factory = client_factory

        self._startup_timeout_seconds = (
            startup_timeout_seconds
        )
        self._call_timeout_seconds = (
            call_timeout_seconds
        )
        self._shutdown_timeout_seconds = (
            shutdown_timeout_seconds
        )

        self._thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None
        self._stop_event: asyncio.Event | None = None

        self._startup_complete = Event()
        self._startup_error: BaseException | None = None

        self._running = False
        self._closed = False

    def start(self) -> None:
        if self._closed:
            raise RuntimeError(
                "MCP invoker has already been closed"
            )

        if self._running:
            return

        self._startup_complete.clear()
        self._startup_error = None

        self._thread = Thread(
            target=self._thread_main,
            name="mcp-client",
            daemon=True,
        )

        self._thread.start()

        if not self._startup_complete.wait(
            self._startup_timeout_seconds
        ):
            raise RuntimeError(
                "timed out starting MCP client"
            )

        if self._startup_error is not None:
            raise RuntimeError(
                "failed to start MCP client"
            ) from self._startup_error

        self._running = True

    def _thread_main(self) -> None:
        try:
            asyncio.run(
                self._run_client()
            )
        except BaseException as exc:
            self._startup_error = exc
            self._startup_complete.set()

    async def _run_client(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        try:
            async with self._client_factory(
                self._server
            ) as client:
                self._client = client

                self._startup_complete.set()

                await self._stop_event.wait()
        except BaseException as exc:
            if not self._startup_complete.is_set():
                self._startup_error = exc
                self._startup_complete.set()
            else:
                raise
        finally:
            self._client = None

    async def _call_tool_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self._client is None:
            raise MCPToolInvocationNotSentError(
                "MCP client is not connected"
            )

        result = await self._client.call_tool(
            tool_name,
            arguments,
        )

        return normalize_mcp_tool_result(
            result
        )

    async def _list_tools_async(
        self,
    ) -> Any:
        if self._client is None:
            raise MCPToolInvocationNotSentError(
                "MCP client is not connected"
            )

        return await self._client.list_tools()

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            not self._running
            or self._loop is None
            or self._client is None
        ):
            raise MCPToolInvocationNotSentError(
                "MCP invoker is not running"
            )

        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(
                tool_name,
                arguments,
            ),
            self._loop,
        )

        try:
            return future.result(
                timeout=self._call_timeout_seconds
            )

        except FutureTimeoutError as exc:
            future.cancel()

            raise MCPToolInvocationUncertainError(
                "MCP tool invocation timed out"
            ) from exc

        except (
            MCPToolExecutionError,
            MCPToolResultShapeError,
            MCPToolInvocationNotSentError,
        ):
            raise

        except Exception as exc:
            raise MCPToolInvocationUncertainError(
                "MCP tool invocation outcome is uncertain"
            ) from exc

    def list_tools(
        self,
    ) -> Any:
        if (
            not self._running
            or self._loop is None
            or self._client is None
        ):
            raise MCPToolInvocationNotSentError(
                "MCP invoker is not running"
            )

        future = asyncio.run_coroutine_threadsafe(
            self._list_tools_async(),
            self._loop,
        )

        try:
            return future.result(
                timeout=self._call_timeout_seconds
            )

        except FutureTimeoutError as exc:
            future.cancel()

            raise MCPToolInvocationUncertainError(
                "MCP list_tools invocation timed out"
            ) from exc

        except MCPToolInvocationNotSentError:
            raise

        except Exception as exc:
            raise RuntimeError(
                "failed to list MCP tools"
            ) from exc

    def close(self) -> None:
        if self._closed:
            return

        if (
            self._running
            and self._loop is not None
            and self._stop_event is not None
        ):
            self._loop.call_soon_threadsafe(
                self._stop_event.set
            )

            if self._thread is not None:
                self._thread.join(
                    timeout=self._shutdown_timeout_seconds
                )

                if self._thread.is_alive():
                    raise RuntimeError(
                        "timed out stopping MCP client"
                    )

        self._running = False
        self._closed = True

    def __enter__(
        self,
    ) -> "PersistentMCPToolInvoker":
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()