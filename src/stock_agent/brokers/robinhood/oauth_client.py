from contextlib import asynccontextmanager
from typing import AsyncIterator
import webbrowser
from urllib.parse import parse_qs, urlparse

import httpx2
from pydantic import AnyUrl

from mcp import Client
from mcp.client.auth import (
    AuthorizationCodeResult,
    OAuthClientProvider,
    TokenStorage,
)
from mcp.client.streamable_http import (
    streamable_http_client,
)
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from stock_agent.brokers.robinhood.oauth_storage import (
    KeyringTokenStorage,
)


ROBINHOOD_MCP_URL = (
    "https://agent.robinhood.com/mcp/trading"
)

ROBINHOOD_REDIRECT_URI = (
    "http://localhost:8765/callback"
)


class InMemoryTokenStorage(TokenStorage):
    def __init__(self) -> None:
        self._tokens: OAuthToken | None = None
        self._client_info: (
            OAuthClientInformationFull | None
        ) = None

    async def get_tokens(
        self,
    ) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(
        self,
        tokens: OAuthToken,
    ) -> None:
        self._tokens = tokens

    async def get_client_info(
        self,
    ) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(
        self,
        client_info: OAuthClientInformationFull,
    ) -> None:
        self._client_info = client_info


async def open_authorization_url(
    auth_url: str,
) -> None:
    print(
        "\nOpen this Robinhood authorization URL:\n"
    )
    print(auth_url)
    print()

    webbrowser.open(auth_url)


async def read_authorization_callback(
) -> AuthorizationCodeResult:
    print(
        "\nAfter approving Robinhood access, "
        "copy the COMPLETE localhost callback URL "
        "from the browser address bar."
    )

    callback_url = input(
        "\nCallback URL: "
    ).strip()

    params = parse_qs(
        urlparse(callback_url).query
    )

    if "code" not in params:
        raise ValueError(
            "callback URL does not contain code"
        )

    return AuthorizationCodeResult(
        code=params["code"][0],
        state=params.get(
            "state",
            [None],
        )[0],
        iss=params.get(
            "iss",
            [None],
        )[0],
    )


class RobinhoodOAuthClientFactory:
    def __init__(
        self,
        *,
        storage: TokenStorage | None = None,
    ) -> None:
        self._storage = (
            storage
            if storage is not None
            else KeyringTokenStorage()
        )

    @asynccontextmanager
    async def __call__(
        self,
        server_url: str,
    ) -> AsyncIterator[Client]:
        oauth = OAuthClientProvider(
            server_url=server_url,
            client_metadata=OAuthClientMetadata(
                client_name=(
                    "stock-agent local development"
                ),
                redirect_uris=[
                    AnyUrl(
                        ROBINHOOD_REDIRECT_URI
                    )
                ],
                grant_types=[
                    "authorization_code",
                    "refresh_token",
                ],
                response_types=[
                    "code",
                ],
                scope="internal",
            ),
            storage=self._storage,
            redirect_handler=(
                open_authorization_url
            ),
            callback_handler=(
                read_authorization_callback
            ),
        )

        async with httpx2.AsyncClient(
            auth=oauth
        ) as http_client:
            transport = streamable_http_client(
                server_url,
                http_client=http_client,
                terminate_on_close=False,
            )

            async with Client(
                transport
            ) as client:
                yield client