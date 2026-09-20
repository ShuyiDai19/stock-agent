import unittest
from datetime import (
    datetime,
    timezone,
)

from stock_agent.strategy.market_session import (
    RegularMarketSessionStatus,
    XnysRegularMarketSessionResolver,
)


class MarketSessionTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.resolver = (
            XnysRegularMarketSessionResolver()
        )

    def test_regular_day_before_open(
        self,
    ) -> None:
        result = (
            self.resolver.resolve(
                datetime(
                    2026,
                    9,
                    18,
                    13,
                    0,
                    tzinfo=timezone.utc,
                )
            )
        )

        self.assertEqual(
            result.status,
            RegularMarketSessionStatus
            .BEFORE_OPEN,
        )

    def test_regular_day_during_session(
        self,
    ) -> None:
        result = (
            self.resolver.resolve(
                datetime(
                    2026,
                    9,
                    18,
                    14,
                    0,
                    tzinfo=timezone.utc,
                )
            )
        )

        self.assertEqual(
            result.status,
            RegularMarketSessionStatus
            .OPEN,
        )

        self.assertTrue(
            result.is_open
        )

        self.assertEqual(
            result.opens_at,
            datetime(
                2026,
                9,
                18,
                13,
                30,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            result.closes_at,
            datetime(
                2026,
                9,
                18,
                20,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def test_regular_day_after_close(
        self,
    ) -> None:
        result = (
            self.resolver.resolve(
                datetime(
                    2026,
                    9,
                    18,
                    20,
                    1,
                    tzinfo=timezone.utc,
                )
            )
        )

        self.assertEqual(
            result.status,
            RegularMarketSessionStatus
            .AFTER_CLOSE,
        )

    def test_weekend_has_no_session(
        self,
    ) -> None:
        result = (
            self.resolver.resolve(
                datetime(
                    2026,
                    9,
                    19,
                    14,
                    0,
                    tzinfo=timezone.utc,
                )
            )
        )

        self.assertEqual(
            result.status,
            RegularMarketSessionStatus
            .NO_SESSION,
        )

        self.assertIsNone(
            result.opens_at
        )

        self.assertIsNone(
            result.closes_at
        )

    def test_thanksgiving_has_no_session(
        self,
    ) -> None:
        result = (
            self.resolver.resolve(
                datetime(
                    2026,
                    11,
                    26,
                    16,
                    0,
                    tzinfo=timezone.utc,
                )
            )
        )

        self.assertEqual(
            result.status,
            RegularMarketSessionStatus
            .NO_SESSION,
        )

    def test_early_close_is_respected(
        self,
    ) -> None:
        # Friday after Thanksgiving:
        # NYSE closes at 1 PM ET.
        before_close = (
            self.resolver.resolve(
                datetime(
                    2026,
                    11,
                    27,
                    17,
                    59,
                    tzinfo=timezone.utc,
                )
            )
        )

        after_close = (
            self.resolver.resolve(
                datetime(
                    2026,
                    11,
                    27,
                    18,
                    1,
                    tzinfo=timezone.utc,
                )
            )
        )

        self.assertEqual(
            before_close.status,
            RegularMarketSessionStatus
            .OPEN,
        )

        self.assertEqual(
            before_close.closes_at,
            datetime(
                2026,
                11,
                27,
                18,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            after_close.status,
            RegularMarketSessionStatus
            .AFTER_CLOSE,
        )


if __name__ == "__main__":
    unittest.main()