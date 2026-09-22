import unittest

from stock_agent.brokers.robinhood.option_exposure_reader import (
    MCPRobinhoodOptionExposureReader,
)


class SequencedInvoker:
    def __init__(
        self,
        results,
    ) -> None:
        self.results = list(
            results
        )
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        if not self.results:
            raise AssertionError(
                "result sequence exhausted"
            )

        return self.results.pop(0)

class MCPRobinhoodOptionExposureReaderTests(
    unittest.TestCase
):
    def test_empty_positions_have_no_exposure(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                {
                    "data": {
                        "positions": [],
                    },
                    "guide": {},
                }
            ]
        )

        result = (
            MCPRobinhoodOptionExposureReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                )
            )
        )

        self.assertFalse(
            result.has_open_position
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_option_positions",
                    {
                        "account_number":
                            "account-0000",
                    },
                ),
            ],
        )

    def test_any_position_counts_as_exposure(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                {
                    "data": {
                        "positions": [
                            {
                                "unknown_future_field":
                                    "value"
                            }
                        ],
                    }
                }
            ]
        )

        result = (
            MCPRobinhoodOptionExposureReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                )
            )
        )

        self.assertTrue(
            result.has_open_position
        )

    def test_reads_next_page_for_exposure(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                {
                    "data": {
                        "positions": [],
                        "next": (
                            "https://example.com/"
                            "?cursor=cursor-2"
                        ),
                    }
                },
                {
                    "data": {
                        "positions": [
                            {
                                "position": "present"
                            }
                        ],
                        "next": None,
                    }
                },
            ]
        )

        result = (
            MCPRobinhoodOptionExposureReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                )
            )
        )

        self.assertTrue(
            result.has_open_position
        )

        self.assertEqual(
            invoker.calls[1],
            (
                "get_option_positions",
                {
                    "account_number":
                        "account-0000",
                    "cursor":
                        "cursor-2",
                },
            ),
        )

    def test_malformed_positions_fail_closed(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                {
                    "data": {
                        "positions": "bad"
                    }
                }
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "positions",
        ):
            (
                MCPRobinhoodOptionExposureReader(
                    invoker
                ).read(
                    account_number=(
                        "account-0000"
                    )
                )
            )

    def test_malformed_position_row_is_rejected(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                {
                    "data": {
                        "positions": [
                            "bad"
                        ]
                    }
                }
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "must be a mapping",
        ):
            (
                MCPRobinhoodOptionExposureReader(
                    invoker
                ).read(
                    account_number=(
                        "account-0000"
                    )
                )
            )

