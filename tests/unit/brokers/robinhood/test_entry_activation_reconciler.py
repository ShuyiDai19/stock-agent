import unittest
from unittest.mock import patch

from stock_agent.brokers.robinhood.entry_activation_reconciler import (
    RobinhoodEquityEntryActivationReconciler,
)


class FakeInvoker:
    pass


class FakeJournal:
    pass


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


if __name__ == "__main__":
    unittest.main()