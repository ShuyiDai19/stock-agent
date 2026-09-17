import unittest

from mcp.shared.auth import OAuthToken

from stock_agent.brokers.robinhood.oauth_storage import (
    KeyringTokenStorage,
)


class FakeKeyringBackend:
    def __init__(self) -> None:
        self.values = {}

    def get_password(
        self,
        service_name,
        username,
    ):
        return self.values.get(
            (
                service_name,
                username,
            )
        )

    def set_password(
        self,
        service_name,
        username,
        password,
    ):
        self.values[
            (
                service_name,
                username,
            )
        ] = password

    def delete_password(
        self,
        service_name,
        username,
    ):
        self.values.pop(
            (
                service_name,
                username,
            )
        )


class KeyringTokenStorageTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_starts_without_tokens(
        self,
    ) -> None:
        storage = KeyringTokenStorage(
            backend=FakeKeyringBackend(),
        )

        self.assertIsNone(
            await storage.get_tokens()
        )

    async def test_round_trips_tokens(
        self,
    ) -> None:
        backend = FakeKeyringBackend()

        storage = KeyringTokenStorage(
            backend=backend,
        )

        tokens = OAuthToken(
            access_token="access-token",
            token_type="Bearer",
            refresh_token="refresh-token",
        )

        await storage.set_tokens(
            tokens
        )

        restored = await storage.get_tokens()

        self.assertEqual(
            restored,
            tokens,
        )