import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.equity_exit_price_provider import (
    RobinhoodEquityExitPriceProvider,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.domain import (
    AssetType,
    QuoteSnapshot,
)


_NOW = datetime(
    2026,
    9,
    24,
    20,
    0,
    tzinfo=timezone.utc,
)


class FakeQuoteProvider:
    def __init__(
        self,
        quote: QuoteSnapshot,
    ) -> None:
        self.quote = quote
        self.calls = []

    def get_quote(
        self,
        symbol: str,
    ) -> QuoteSnapshot:
        self.calls.append(
            symbol
        )

        return self.quote


def make_equity_request(
) -> RobinhoodExitOrderRequest:
    return RobinhoodExitOrderRequest(
        position_id="position-1",
        account_number=(
            "agentic-account"
        ),
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        quantity=Decimal("0.031"),
        action=(
            RobinhoodExitAction
            .EQUITY_SELL
        ),
        option_id=None,
    )


class RobinhoodEquityExitPriceProviderTests(
    unittest.TestCase
):
    def test_maps_equity_quote_to_exit_price(
        self,
    ) -> None:
        quote_provider = (
            FakeQuoteProvider(
                QuoteSnapshot(
                    symbol="AAPL",
                    bid=Decimal(
                        "102.85"
                    ),
                    observed_at=_NOW,
                )
            )
        )

        provider = (
            RobinhoodEquityExitPriceProvider(
                quote_provider
            )
        )

        result = (
            provider.get_exit_price(
                make_equity_request()
            )
        )

        self.assertEqual(
            result.symbol,
            "AAPL",
        )

        self.assertEqual(
            result.executable_bid,
            Decimal("102.85"),
        )

        self.assertEqual(
            result.observed_at,
            _NOW,
        )

        self.assertIsNone(
            result.option_id
        )

        self.assertEqual(
            quote_provider.calls,
            [
                "AAPL",
            ],
        )

    def test_mismatched_quote_symbol_fails_closed(
        self,
    ) -> None:
        quote_provider = (
            FakeQuoteProvider(
                QuoteSnapshot(
                    symbol="MSFT",
                    bid=Decimal("400"),
                    observed_at=_NOW,
                )
            )
        )

        provider = (
            RobinhoodEquityExitPriceProvider(
                quote_provider
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "quote symbol",
        ):
            provider.get_exit_price(
                make_equity_request()
            )

    def test_option_request_is_rejected(
        self,
    ) -> None:
        quote_provider = (
            FakeQuoteProvider(
                QuoteSnapshot(
                    symbol="AAPL",
                    bid=Decimal("100"),
                    observed_at=_NOW,
                )
            )
        )

        provider = (
            RobinhoodEquityExitPriceProvider(
                quote_provider
            )
        )

        request = (
            RobinhoodExitOrderRequest(
                position_id=(
                    "option-position-1"
                ),
                account_number=(
                    "agentic-account"
                ),
                asset_type=(
                    AssetType.OPTION
                ),
                symbol="AAPL",
                quantity=Decimal("1"),
                action=(
                    RobinhoodExitAction
                    .OPTION_SELL_TO_CLOSE
                ),
                option_id=(
                    "option-contract-1"
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "equity request",
        ):
            provider.get_exit_price(
                request
            )


if __name__ == "__main__":
    unittest.main()