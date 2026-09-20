import unittest
from dataclasses import replace
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from stock_agent.domain import (
    AssetType,
)
from stock_agent.orchestration.portfolio_state import (
    UnsupportedOpenPositionRiskError,
    load_open_position_risk_snapshots,
)
from stock_agent.state import (
    PositionRuntimeState,
    PositionStateStatus,
)


_NOW = datetime(
    2026,
    9,
    18,
    18,
    0,
    tzinfo=timezone.utc,
)


def position(
    symbol: str,
    *,
    status=PositionStateStatus.ACTIVE,
    entry_price: str = "100",
    quantity: str | None = None,
) -> PositionRuntimeState:
    if quantity is None:
        quantity = (
            "0"
            if status
            is PositionStateStatus.CLOSED
            else "0.05"
        )

    return PositionRuntimeState(
        position_id=(
            f"agentic-account:"
            f"equity:{symbol}:"
            f"order-{symbol}"
        ),
        account_number=(
            "agentic-account"
        ),
        asset_type=(
            AssetType.EQUITY
        ),
        symbol=symbol,
        opening_order_id=(
            f"order-{symbol}"
        ),
        entry_price=Decimal(
            entry_price
        ),
        remaining_quantity=Decimal(
            quantity
        ),
        opened_at=_NOW,
        highest_executable_bid=Decimal(
            entry_price
        ),
        trailing_armed=False,
        trailing_armed_at=None,
        activation_gain_ratio=Decimal(
            "0.04"
        ),
        drawdown_ratio=Decimal(
            "0.02"
        ),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
        status=status,
    )


class FakeStore:
    def __init__(
        self,
        states,
    ) -> None:
        self.states = list(
            states
        )

        self.calls = []

    def list_by_status(
        self,
        *,
        account_number,
        statuses,
    ):
        self.calls.append(
            (
                account_number,
                statuses,
            )
        )

        return [
            state
            for state in self.states
            if (
                state.account_number
                == account_number
                and state.status
                in statuses
            )
        ]


class PortfolioStateTests(
    unittest.TestCase
):
    def test_active_position_becomes_risk_snapshot(
        self,
    ) -> None:
        store = FakeStore(
            [
                position(
                    "AAPL",
                    entry_price="100",
                    quantity="0.05",
                )
            ]
        )

        snapshots = (
            load_open_position_risk_snapshots(
                store,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            len(snapshots),
            1,
        )

        self.assertEqual(
            snapshots[0].symbol,
            "AAPL",
        )

        self.assertEqual(
            snapshots[0].asset_type,
            AssetType.EQUITY,
        )

        self.assertEqual(
            snapshots[0].opening_cost,
            Decimal("5.00"),
        )

    def test_closing_position_still_reserves_capacity(
        self,
    ) -> None:
        store = FakeStore(
            [
                position(
                    "AAPL",
                    status=(
                        PositionStateStatus
                        .CLOSING
                    ),
                )
            ]
        )

        snapshots = (
            load_open_position_risk_snapshots(
                store,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            len(snapshots),
            1,
        )

        self.assertEqual(
            snapshots[0].symbol,
            "AAPL",
        )

    def test_reconciliation_required_still_reserves_capacity(
        self,
    ) -> None:
        store = FakeStore(
            [
                position(
                    "AAPL",
                    status=(
                        PositionStateStatus
                        .RECONCILIATION_REQUIRED
                    ),
                )
            ]
        )

        snapshots = (
            load_open_position_risk_snapshots(
                store,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            len(snapshots),
            1,
        )

    def test_closed_position_is_excluded(
        self,
    ) -> None:
        store = FakeStore(
            [
                position(
                    "AAPL",
                    status=(
                        PositionStateStatus
                        .CLOSED
                    ),
                    quantity="0",
                )
            ]
        )

        snapshots = (
            load_open_position_risk_snapshots(
                store,
                account_number=(
                    "agentic-account"
                ),
            )
        )

        self.assertEqual(
            snapshots,
            (),
        )

    def test_non_equity_open_position_fails_closed(
        self,
    ) -> None:
        equity = position(
            "AAPL"
        )

        option = replace(
            equity,
            position_id=(
                "agentic-account:"
                "option:AAPL:"
                "option-order-1"
            ),
            asset_type=(
                AssetType.OPTION
            ),
            opening_order_id=(
                "option-order-1"
            ),
            option_id=(
                "option-contract-1"
            ),
        )

        store = FakeStore(
            [
                option
            ]
        )

        with self.assertRaisesRegex(
            UnsupportedOpenPositionRiskError,
            "non-equity position",
        ):
            load_open_position_risk_snapshots(
                store,
                account_number=(
                    "agentic-account"
                ),
            )


if __name__ == "__main__":
    unittest.main()