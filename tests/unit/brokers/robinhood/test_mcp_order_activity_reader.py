import unittest
from datetime import (
    datetime,
    timezone,
)

from stock_agent.brokers.robinhood.mcp_order_activity_reader import (
    MCPRobinhoodOrderActivityReader,
)


_EVALUATED_AT = datetime(
    2026,
    9,
    18,
    15,
    0,
    tzinfo=timezone.utc,
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
                "fake results exhausted"
            )

        return self.results.pop(0)


def page(
    orders,
    *,
    next_value=None,
):
    return {
        "data": {
            "orders": orders,
            "next": next_value,
        }
    }

class MCPRobinhoodOrderActivityReaderTests(
    unittest.TestCase
):
    def test_empty_histories_are_clean(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page([]),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertFalse(
            result.has_open_equity_order
        )
        self.assertFalse(
            result.has_open_option_order
        )
        self.assertFalse(
            result.has_opening_order_today
        )

        self.assertEqual(
            invoker.calls,
            [
                (
                    "get_equity_orders",
                    {
                        "account_number":
                            "account-0000",
                    },
                ),
                (
                    "get_option_orders",
                    {
                        "account_number":
                            "account-0000",
                    },
                ),
            ],
        )

    def test_open_equity_order_is_detected(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [
                        {
                            "state":
                                "confirmed",
                            "side":
                                "buy",
                        }
                    ]
                ),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertTrue(
            result.has_open_equity_order
        )

    def test_unknown_state_is_treated_as_open(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [
                        {
                            "state":
                                "new_broker_state",
                            "side":
                                "buy",
                        }
                    ]
                ),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertTrue(
            result.has_open_equity_order
        )

    def test_filled_equity_buy_today_counts_as_opening(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [
                        {
                            "state":
                                "filled",
                            "side":
                                "buy",
                            "created_at":
                                (
                                    "2026-09-18"
                                    "T14:30:00Z"
                                ),
                        }
                    ]
                ),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertFalse(
            result.has_open_equity_order
        )

        self.assertTrue(
            result.has_opening_order_today
        )

    def test_equity_sell_today_is_not_opening(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [
                        {
                            "state":
                                "filled",
                            "side":
                                "sell",
                            "created_at":
                                (
                                    "2026-09-18"
                                    "T14:30:00Z"
                                ),
                        }
                    ]
                ),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertFalse(
            result.has_opening_order_today
        )

    def test_option_buy_to_open_today_counts_as_opening(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page([]),
                page(
                    [
                        {
                            "state":
                                "filled",
                            "side":
                                "buy",
                            "position_effect":
                                "open",
                            "created_at":
                                (
                                    "2026-09-18"
                                    "T14:30:00Z"
                                ),
                        }
                    ]
                ),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertTrue(
            result.has_opening_order_today
        )

    def test_previous_day_opening_does_not_count_today(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [
                        {
                            "state":
                                "filled",
                            "side":
                                "buy",
                            "created_at":
                                (
                                    "2026-09-17"
                                    "T15:00:00Z"
                                ),
                        }
                    ]
                ),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertFalse(
            result.has_opening_order_today
        )

    def test_closed_order_without_submission_time_fails_closed(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [
                        {
                            "state":
                                "filled",
                            "side":
                                "buy",
                        }
                    ]
                ),
                page([]),
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "submission timestamp",
        ):
            (
                MCPRobinhoodOrderActivityReader(
                    invoker
                ).read(
                    account_number=(
                        "account-0000"
                    ),
                    evaluated_at=(
                        _EVALUATED_AT
                    ),
                )
            )

    def test_reads_all_equity_order_pages(
        self,
    ) -> None:
        invoker = SequencedInvoker(
            [
                page(
                    [],
                    next_value=(
                        "https://example.invalid/"
                        "orders?cursor=page-2"
                    ),
                ),
                page(
                    [
                        {
                            "state":
                                "confirmed",
                            "side":
                                "buy",
                        }
                    ]
                ),
                page([]),
            ]
        )

        result = (
            MCPRobinhoodOrderActivityReader(
                invoker
            ).read(
                account_number=(
                    "account-0000"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )
        )

        self.assertTrue(
            result.has_open_equity_order
        )

        self.assertEqual(
            invoker.calls[1][1],
            {
                "account_number":
                    "account-0000",
                "cursor":
                    "page-2",
            },
        )