import unittest
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import replace


from stock_agent.brokers.robinhood.position_reconciliation import (
    EquityPositionReconciliationIssue,
    reconcile_equity_positions,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
    RobinhoodEquityPositionType,
)
from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
    PositionStateStatus,
)


_NOW = datetime(
    2026,
    9,
    17,
    tzinfo=timezone.utc,
)


def make_local_state(
    *,
    quantity: Decimal = Decimal("1"),
    entry_price: Decimal = Decimal("100"),
) -> PositionRuntimeState:
    return PositionRuntimeState(
        position_id="position-1",
        account_number="agentic-account",
        asset_type=AssetType.EQUITY,
        symbol="AAPL",
        opening_order_id="opening-order-1",
        entry_price=entry_price,
        remaining_quantity=quantity,
        opened_at=_NOW,
        highest_executable_bid=(
            entry_price
        ),
        trailing_armed=False,
        trailing_armed_at=None,
        activation_gain_ratio=(
            Decimal("0.04")
        ),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
    )


def make_broker_position(
    *,
    quantity: Decimal = Decimal("1"),
    sellable: Decimal = Decimal("1"),
    average_buy_price: (
        Decimal | None
    ) = Decimal("100"),
    position_type: (
        RobinhoodEquityPositionType
    ) = RobinhoodEquityPositionType.LONG,
) -> RobinhoodEquityPositionSnapshot:
    return RobinhoodEquityPositionSnapshot(
        symbol="AAPL",
        quantity=quantity,
        intraday_quantity=Decimal("0"),
        average_buy_price=(
            average_buy_price
        ),
        shares_available_for_sells=(
            sellable
        ),
        position_type=position_type,
    )

class EquityPositionReconciliationTests(
    unittest.TestCase
):
    def test_exact_position_matches(
        self,
    ) -> None:
        outcomes = reconcile_equity_positions(
            account_number="agentic-account",
            local_states=[
                make_local_state()
            ],
            broker_positions=[
                make_broker_position()
            ],
        )

        self.assertEqual(
            len(outcomes),
            1,
        )

        self.assertTrue(
            outcomes[0].matched
        )

        self.assertEqual(
            outcomes[0].issues,
            frozenset(),
        )

    def test_missing_broker_position(
        self,
    ) -> None:
        outcome = reconcile_equity_positions(
            account_number="agentic-account",
            local_states=[
                make_local_state()
            ],
            broker_positions=[],
        )[0]

        self.assertEqual(
            outcome.issues,
            frozenset(
                {
                    EquityPositionReconciliationIssue
                    .BROKER_POSITION_MISSING
                }
            ),
        )

    def test_broker_only_position(
        self,
    ) -> None:
        outcome = reconcile_equity_positions(
            account_number="agentic-account",
            local_states=[],
            broker_positions=[
                make_broker_position()
            ],
        )[0]

        self.assertEqual(
            outcome.issues,
            frozenset(
                {
                    EquityPositionReconciliationIssue
                    .LOCAL_POSITION_MISSING
                }
            ),
        )

    def test_quantity_and_sellability_can_both_mismatch(
        self,
    ) -> None:
        outcome = reconcile_equity_positions(
            account_number="agentic-account",
            local_states=[
                make_local_state(
                    quantity=Decimal("1")
                )
            ],
            broker_positions=[
                make_broker_position(
                    quantity=Decimal("0.75"),
                    sellable=Decimal("0.50"),
                )
            ],
        )[0]

        self.assertEqual(
            outcome.issues,
            frozenset(
                {
                    EquityPositionReconciliationIssue
                    .QUANTITY_MISMATCH,
                    EquityPositionReconciliationIssue
                    .SELLABILITY_RESTRICTED,
                }
            ),
        )

    def test_average_cost_difference_is_not_a_hard_mismatch(
        self,
    ) -> None:
        outcome = reconcile_equity_positions(
            account_number="agentic-account",
            local_states=[
                make_local_state(
                    entry_price=Decimal("100")
                )
            ],
            broker_positions=[
                make_broker_position(
                    average_buy_price=(
                        Decimal("125")
                    )
                )
            ],
        )[0]

        self.assertTrue(
            outcome.matched
        )

    def test_short_position_is_unsupported(
        self,
    ) -> None:
        outcome = reconcile_equity_positions(
            account_number="agentic-account",
            local_states=[
                make_local_state()
            ],
            broker_positions=[
                make_broker_position(
                    position_type=(
                        RobinhoodEquityPositionType.SHORT
                    )
                )
            ],
        )[0]

        self.assertIn(
            EquityPositionReconciliationIssue
            .UNSUPPORTED_POSITION_TYPE,
            outcome.issues,
        )

    def test_closing_position_with_reserved_shares_still_matches(
        self,
    ) -> None:
        local_state = replace(
            make_local_state(),
            status=PositionStateStatus.CLOSING,
            remaining_quantity=Decimal("1"),
        )

        broker_position = replace(
            make_broker_position(),
            quantity=Decimal("1"),
            shares_available_for_sells=Decimal("0"),
        )

        outcomes = reconcile_equity_positions(
            account_number=local_state.account_number,
            local_states=[local_state],
            broker_positions=[broker_position],
        )

        self.assertEqual(
            len(outcomes),
            1,
        )

        outcome = outcomes[0]

        self.assertTrue(
            outcome.matched
        )

        self.assertNotIn(
            EquityPositionReconciliationIssue
            .SELLABILITY_RESTRICTED,
            outcome.issues,
        )