import unittest
from decimal import Decimal

from stock_agent.brokers.robinhood.mcp_position_decoder import (
    decode_robinhood_equity_positions,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionType,
)


class RobinhoodEquityPositionDecoderTests(
    unittest.TestCase
):
    def test_decodes_real_equity_position_shape(
        self,
    ) -> None:
        payload = {
            "data": {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "0.031089",
                        "intraday_quantity":
                            "0.000000",
                        "average_buy_price":
                            "321.660000",
                        "shares_available_for_sells":
                            "0.031089",
                        "type": "long",
                    }
                ]
            }
        }

        positions = (
            decode_robinhood_equity_positions(
                payload
            )
        )

        self.assertEqual(
            len(positions),
            1,
        )

        position = positions[0]

        self.assertEqual(
            position.symbol,
            "AAPL",
        )

        self.assertEqual(
            position.quantity,
            Decimal("0.031089"),
        )

        self.assertEqual(
            position.intraday_quantity,
            Decimal("0.000000"),
        )

        self.assertEqual(
            position.average_buy_price,
            Decimal("321.660000"),
        )

        self.assertEqual(
            position.shares_available_for_sells,
            Decimal("0.031089"),
        )

        self.assertEqual(
            position.position_type,
            RobinhoodEquityPositionType.LONG,
        )

    def test_average_buy_price_may_be_missing(
        self,
    ) -> None:
        payload = {
            "data": {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "0.031089",
                        "intraday_quantity":
                            "0.000000",
                        "shares_available_for_sells":
                            "0.031089",
                        "type": "long",
                    }
                ]
            }
        }

        position = (
            decode_robinhood_equity_positions(
                payload
            )[0]
        )

        self.assertIsNone(
            position.average_buy_price
        )

    def test_sellable_quantity_cannot_exceed_quantity(
        self,
    ) -> None:
        payload = {
            "data": {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "1",
                        "intraday_quantity": "0",
                        "average_buy_price": "100",
                        "shares_available_for_sells":
                            "2",
                        "type": "long",
                    }
                ]
            }
        }

        with self.assertRaises(
            ValueError
        ):
            decode_robinhood_equity_positions(
                payload
            )