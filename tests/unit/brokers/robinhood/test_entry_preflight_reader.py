import unittest
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.brokers.robinhood.entry_funds import (
    RobinhoodEntryFundsSnapshot,
)
from stock_agent.brokers.robinhood.entry_preflight_reader import (
    RobinhoodEquityEntryPreflightReader,
)
from stock_agent.brokers.robinhood.mcp_order_activity_reader import (
    RobinhoodOrderActivityReadResult,
)
from stock_agent.brokers.robinhood.position_reader import (
    RobinhoodEquityPositionReadResult,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
    RobinhoodEquityPositionType,
)
from stock_agent.brokers.robinhood.option_exposure_reader import (
    RobinhoodOptionExposureReadResult,
)
from stock_agent.orchestration.equity_entry_preflight import (
    EquityEntryPreflightDataSource,
    EquityEntryPreflightDataUnavailableError,
)


_EVALUATED_AT = datetime(
    2026,
    9,
    18,
    15,
    0,
    tzinfo=timezone.utc,
)

class FakePositionReader:
    def __init__(
        self,
        positions=(),
    ) -> None:
        self.positions = tuple(
            positions
        )
        self.calls = []

    def read(
        self,
        *,
        account_number,
    ):
        self.calls.append(
            account_number
        )

        return (
            RobinhoodEquityPositionReadResult(
                positions=self.positions
            )
        )


class FakeOrderActivityReader:
    def __init__(
        self,
        result,
    ) -> None:
        self.result = result
        self.calls = []

    def read(
        self,
        *,
        account_number,
        evaluated_at,
    ):
        self.calls.append(
            (
                account_number,
                evaluated_at,
            )
        )

        return self.result


class FakeFundsReader:
    def __init__(
        self,
        result,
    ) -> None:
        self.result = result
        self.calls = []

    def read(
        self,
        *,
        account_number,
    ):
        self.calls.append(
            account_number
        )

        return self.result

class FakeOptionExposureReader:
    def __init__(
        self,
        *,
        has_open_position=False,
    ) -> None:
        self.result = (
            RobinhoodOptionExposureReadResult(
                has_open_position=(
                    has_open_position
                )
            )
        )
        self.calls = []

    def read(
        self,
        *,
        account_number,
    ):
        self.calls.append(
            account_number
        )
        return self.result

class RobinhoodEquityEntryPreflightReaderTests(
    unittest.TestCase
):
    def test_combines_broker_sources_into_snapshot(
        self,
    ) -> None:
        position_reader = (
            FakePositionReader()
        )

        order_reader = (
            FakeOrderActivityReader(
                RobinhoodOrderActivityReadResult(
                    has_open_equity_order=False,
                    has_open_option_order=False,
                    has_opening_order_today=False,
                )
            )
        )

        funds_reader = (
            FakeFundsReader(
                RobinhoodEntryFundsSnapshot(
                    buying_power=Decimal(
                        "90"
                    ),
                    cash=Decimal(
                        "90"
                    ),
                )
            )
        )

        reader = (
            RobinhoodEquityEntryPreflightReader(
                position_reader=(
                    position_reader
                ),
                option_exposure_reader=(
                    FakeOptionExposureReader()
                ),
                order_activity_reader=(
                    order_reader
                ),
                funds_reader=(
                    funds_reader
                ),
            )
        )

        snapshot = reader.read(
            account_number=(
                "account-0000"
            ),
            evaluated_at=(
                _EVALUATED_AT
            ),
        )

        self.assertFalse(
            snapshot.has_existing_position
        )

        self.assertFalse(
            snapshot.has_open_equity_order
        )

        self.assertFalse(
            snapshot.has_open_option_order
        )

        self.assertFalse(
            snapshot.has_opening_order_today
        )

        self.assertEqual(
            snapshot.buying_power,
            Decimal("90"),
        )

        self.assertEqual(
            snapshot.cash,
            Decimal("90"),
        )

    def test_positive_broker_position_sets_existing_position(
        self,
    ) -> None:
        position = (
            RobinhoodEquityPositionSnapshot(
                symbol="AAPL",
                quantity=Decimal("0.05"),
                intraday_quantity=Decimal("0"),
                average_buy_price=Decimal(
                    "100"
                ),
                shares_available_for_sells=Decimal(
                    "0.05"
                ),
                position_type=(
                    RobinhoodEquityPositionType
                    .LONG
                ),
            )
        )

        reader = (
            RobinhoodEquityEntryPreflightReader(
                position_reader=(
                    FakePositionReader(
                        [position]
                    )
                ),
                option_exposure_reader=(
                    FakeOptionExposureReader()
                ),
                order_activity_reader=(
                    FakeOrderActivityReader(
                        RobinhoodOrderActivityReadResult(
                            has_open_equity_order=False,
                            has_open_option_order=False,
                            has_opening_order_today=False,
                        )
                    )
                ),
                funds_reader=(
                    FakeFundsReader(
                        RobinhoodEntryFundsSnapshot(
                            buying_power=Decimal(
                                "90"
                            ),
                            cash=Decimal(
                                "90"
                            ),
                        )
                    )
                ),
            )
        )

        snapshot = reader.read(
            account_number=(
                "account-0000"
            ),
            evaluated_at=(
                _EVALUATED_AT
            ),
        )

        self.assertTrue(
            snapshot.has_existing_position
        )

    def test_dependency_failure_preserves_source_and_cause(
        self,
    ) -> None:
        class FailingPositionReader:
            def read(
                self,
                *,
                account_number,
            ):
                raise RuntimeError(
                    "positions unavailable"
                )

        reader = (
            RobinhoodEquityEntryPreflightReader(
                position_reader=(
                    FailingPositionReader()
                ),
                option_exposure_reader=object(),
                order_activity_reader=object(),
                funds_reader=object(),
            )
        )

        with self.assertRaises(
            EquityEntryPreflightDataUnavailableError
        ) as context:
            reader.read(
                account_number=(
                    "agentic-account"
                ),
                evaluated_at=(
                    _EVALUATED_AT
                ),
            )

        error = context.exception

        self.assertEqual(
            error.source,
            EquityEntryPreflightDataSource
            .POSITIONS,
        )

        self.assertIsInstance(
            error.cause,
            RuntimeError,
        )

        self.assertEqual(
            str(error.cause),
            "positions unavailable",
        )

        self.assertIs(
            error.__cause__,
            error.cause,
        )

    def test_option_position_sets_existing_position(
        self,
    ) -> None:
        reader = (
            RobinhoodEquityEntryPreflightReader(
                position_reader=(
                    FakePositionReader()
                ),
                option_exposure_reader=(
                    FakeOptionExposureReader(
                        has_open_position=True
                    )
                ),
                order_activity_reader=(
                    FakeOrderActivityReader(
                        RobinhoodOrderActivityReadResult(
                            has_open_equity_order=False,
                            has_open_option_order=False,
                            has_opening_order_today=False,
                        )
                    )
                ),
                funds_reader=(
                    FakeFundsReader(
                        RobinhoodEntryFundsSnapshot(
                            buying_power=Decimal(
                                "90"
                            ),
                            cash=Decimal(
                                "90"
                            ),
                        )
                    )
                ),
            )
        )

        snapshot = reader.read(
            account_number="account-0000",
            evaluated_at=_EVALUATED_AT,
        )

        self.assertTrue(
            snapshot.has_existing_position
        )