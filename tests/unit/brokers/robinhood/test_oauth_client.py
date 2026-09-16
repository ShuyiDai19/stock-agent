import unittest

from stock_agent.brokers.robinhood.oauth_client import (
    InMemoryTokenStorage,
)


class InMemoryTokenStorageTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_starts_without_tokens(
        self,
    ) -> None:
        storage = InMemoryTokenStorage()

        self.assertIsNone(
            await storage.get_tokens()
        )

        self.assertIsNone(
            await storage.get_client_info()
        )