from typing import Protocol

import keyring

from mcp.client.auth import TokenStorage
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthToken,
)


class KeyringBackend(Protocol):
    def get_password(
        self,
        service_name: str,
        username: str,
    ) -> str | None:
        ...

    def set_password(
        self,
        service_name: str,
        username: str,
        password: str,
    ) -> None:
        ...

    def delete_password(
        self,
        service_name: str,
        username: str,
    ) -> None:
        ...


class KeyringTokenStorage(TokenStorage):
    TOKENS_KEY = "oauth_tokens"
    CLIENT_INFO_KEY = "oauth_client_info"

    def __init__(
        self,
        *,
        service_name: str = "stock-agent-robinhood-mcp",
        backend: KeyringBackend = keyring,
    ) -> None:
        if not service_name.strip():
            raise ValueError(
                "service_name cannot be empty"
            )

        self._service_name = service_name
        self._backend = backend

    async def get_tokens(
        self,
    ) -> OAuthToken | None:
        raw = self._backend.get_password(
            self._service_name,
            self.TOKENS_KEY,
        )

        if raw is None:
            return None

        return OAuthToken.model_validate_json(
            raw
        )

    async def set_tokens(
        self,
        tokens: OAuthToken,
    ) -> None:
        self._backend.set_password(
            self._service_name,
            self.TOKENS_KEY,
            tokens.model_dump_json(),
        )

    async def get_client_info(
        self,
    ) -> OAuthClientInformationFull | None:
        raw = self._backend.get_password(
            self._service_name,
            self.CLIENT_INFO_KEY,
        )

        if raw is None:
            return None

        return (
            OAuthClientInformationFull
            .model_validate_json(raw)
        )

    async def set_client_info(
        self,
        client_info: OAuthClientInformationFull,
    ) -> None:
        self._backend.set_password(
            self._service_name,
            self.CLIENT_INFO_KEY,
            client_info.model_dump_json(),
        )

    def clear(
        self,
    ) -> None:
        for key in (
            self.TOKENS_KEY,
            self.CLIENT_INFO_KEY,
        ):
            try:
                self._backend.delete_password(
                    self._service_name,
                    key,
                )
            except keyring.errors.PasswordDeleteError:
                pass