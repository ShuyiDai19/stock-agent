import unittest

from stock_agent.brokers.robinhood.mcp_order_pagination import (
    extract_robinhood_order_next_cursor,
)


class RobinhoodOrderPaginationTests(
    unittest.TestCase
):
    def test_missing_next_means_terminal_page(
        self,
    ) -> None:
        payload = {
            "data": {
                "orders": [],
            }
        }

        self.assertIsNone(
            extract_robinhood_order_next_cursor(
                payload
            )
        )

    def test_explicit_none_means_terminal_page(
        self,
    ) -> None:
        payload = {
            "data": {
                "orders": [],
                "next": None,
            }
        }

        self.assertIsNone(
            extract_robinhood_order_next_cursor(
                payload
            )
        )

    def test_extracts_cursor_from_next_url(
        self,
    ) -> None:
        payload = {
            "data": {
                "orders": [],
                "next": (
                    "https://api.robinhood.com/"
                    "orders/?cursor=cursor-123"
                ),
            }
        }

        self.assertEqual(
            extract_robinhood_order_next_cursor(
                payload
            ),
            "cursor-123",
        )

    def test_conflicting_next_metadata_raises(
        self,
    ) -> None:
        payload = {
            "next": None,
            "data": {
                "orders": [],
                "next": (
                    "https://api.robinhood.com/"
                    "orders/?cursor=cursor-123"
                ),
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "metadata conflicts",
        ):
            extract_robinhood_order_next_cursor(
                payload
            )

    def test_invalid_next_url_raises(
        self,
    ) -> None:
        payload = {
            "data": {
                "orders": [],
                "next": "not-a-url",
            }
        }

        with self.assertRaisesRegex(
            ValueError,
            "HTTPS URL",
        ):
            extract_robinhood_order_next_cursor(
                payload
            )


if __name__ == "__main__":
    unittest.main()