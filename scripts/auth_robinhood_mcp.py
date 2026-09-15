import asyncio
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


MCP_URL = (
    "https://agent.robinhood.com/mcp/trading"
)

REDIRECT_URI = (
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


async def handle_redirect(
    auth_url: str,
) -> None:
    print(
        "\nOpen this Robinhood authorization URL:\n"
    )
    print(auth_url)
    print()

    webbrowser.open(auth_url)


async def handle_callback(
) -> AuthorizationCodeResult:
    print(
        "\nAfter approving Robinhood access, "
        "your browser may fail to load the localhost "
        "callback page."
    )

    print(
        "Copy the COMPLETE URL from the browser "
        "address bar and paste it here."
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


async def main() -> None:
    storage = InMemoryTokenStorage()

    oauth = OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name=(
                "stock-agent local development"
            ),
            redirect_uris=[
                AnyUrl(
                    REDIRECT_URI
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
        storage=storage,
        redirect_handler=handle_redirect,
        callback_handler=handle_callback,
    )

    async with httpx2.AsyncClient(
        auth=oauth
    ) as http_client:
        transport = streamable_http_client(
            MCP_URL,
            http_client=http_client,
        )

        async with Client(
            transport
        ) as client:
            result = await client.list_tools()

            print(
                "\nConnected successfully."
            )

            print(
                "\nAvailable tools:"
            )

            for tool in result.tools:
                print(
                    f"- {tool.name}"
                )


if __name__ == "__main__":
    asyncio.run(
        main()
    )