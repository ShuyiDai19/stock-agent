import unittest
from unittest.mock import patch

from stock_agent.brokers.robinhood.entry_activation_reconciler import (
    RobinhoodEquityEntryActivationReconciler,
)


class FakeInvoker:
    pass


class FakeJournal:
    def __init__(self) -> None:
        self.list_acknowledged_calls = []

    def list_acknowledged(
        self,
        *,
        account_number: str,
    ):
        self.list_acknowledged_calls.append(
            account_number
        )
        return []


class FakeStore:
    pass


class FakeQuoteProvider:
    pass


class RobinhoodEquityEntryActivationReconcilerTests(
    unittest.TestCase
):
    @patch(
        "stock_agent.brokers.robinhood."
        "entry_activation_reconciler."
        "activate_acknowledged_equity_entries"
    )
    def test_reconcile_forwards_dependencies(
        self,
        activate_mock,
    ) -> None:
        activate_mock.return_value = []

        invoker = FakeInvoker()
        journal = FakeJournal()
        store = FakeStore()
        quote_provider = (
            FakeQuoteProvider()
        )

        reconciler = (
            RobinhoodEquityEntryActivationReconciler(
                invoker,
                journal,
                store,
                quote_provider,
            )
        )

        result = reconciler.reconcile(
            account_number=(
                "agentic-account"
            )
        )

        self.assertEqual(
            result,
            (),
        )

        self.assertEqual(
            journal.list_acknowledged_calls,
            [
                "agentic-account",
            ],
        )

        activate_mock.assert_called_once_with(
            invoker,
            journal,
            store,
            quote_provider,
            account_number=(
                "agentic-account"
            ),
        )

    def test_rejects_empty_account_number(
        self,
    ) -> None:
        reconciler = (
            RobinhoodEquityEntryActivationReconciler(
                FakeInvoker(),
                FakeJournal(),
                FakeStore(),
                FakeQuoteProvider(),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "account_number cannot be empty",
        ):
            reconciler.reconcile(
                account_number=" "
            )

    def test_blocks_when_acknowledged_entry_remains(
        self,
    ) -> None:
        class Journal:
            def list_acknowledged(
                self,
                *,
                account_number,
            ):
                return [
                    object()
                ]

        invoker = object()
        journal = Journal()
        store = object()
        quote_provider = object()

        reconciler = (
            RobinhoodEquityEntryActivationReconciler(
                invoker,
                journal,
                store,
                quote_provider,
            )
        )

        with patch(
            "stock_agent.brokers.robinhood."
            "entry_activation_reconciler."
            "activate_acknowledged_equity_entries",
            return_value=[],
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "acknowledged orders unresolved",
            ):
                reconciler.reconcile(
                    account_number=(
                        "agentic-account"
                    )
                )




if __name__ == "__main__":
    unittest.main()