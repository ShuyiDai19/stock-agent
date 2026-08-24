import unittest

from stock_agent.brokers.robinhood import (
    parse_live_execution_enabled,
)


class RobinhoodConfigTests(unittest.TestCase):
    def test_defaults_to_disabled_when_value_missing(
        self,
    ) -> None:
        self.assertFalse(
            parse_live_execution_enabled(None)
        )

    def test_parses_false(
        self,
    ) -> None:
        self.assertFalse(
            parse_live_execution_enabled("false")
        )

    def test_parses_true(
        self,
    ) -> None:
        self.assertTrue(
            parse_live_execution_enabled("true")
        )

    def test_normalizes_whitespace_and_case(
        self,
    ) -> None:
        self.assertTrue(
            parse_live_execution_enabled(
                "  TRUE  "
            )
        )

    def test_rejects_ambiguous_value(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ENABLE_LIVE_EXECUTION",
        ):
            parse_live_execution_enabled(
                "yes"
            )

    def test_rejects_empty_value(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ENABLE_LIVE_EXECUTION",
        ):
            parse_live_execution_enabled(
                ""
            )


if __name__ == "__main__":
    unittest.main()