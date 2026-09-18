import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood.position_reconciliation import (
    EquityPositionReconciliationIssue,
    EquityPositionReconciliationOutcome,
)
from stock_agent.brokers.robinhood.position_reconciliation_policy import (
    EquityPositionReconciliationAction,
    decide_equity_position_reconciliation,
)
from stock_agent.brokers.robinhood.position_snapshots import (
    RobinhoodEquityPositionSnapshot,
    RobinhoodEquityPositionType,
)
from stock_agent.domain import AssetType
from stock_agent.state.models import (
    PositionRuntimeState,
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
        highest_executable_bid=entry_price,
        trailing_armed=False,
        trailing_armed_at=None,
        activation_gain_ratio=Decimal("0.04"),
        drawdown_ratio=Decimal("0.02"),
        last_quote_at=_NOW,
        last_reconciled_at=_NOW,
    )


def make_broker_position(
    *,
    quantity: Decimal = Decimal("1"),
    sellable: Decimal = Decimal("1"),
    average_buy_price: Decimal | None = Decimal("100"),
    position_type: RobinhoodEquityPositionType = (
        RobinhoodEquityPositionType.LONG
    ),
) -> RobinhoodEquityPositionSnapshot:
    return RobinhoodEquityPositionSnapshot(
        symbol="AAPL",
        quantity=quantity,
        intraday_quantity=Decimal("0"),
        average_buy_price=average_buy_price,
        shares_available_for_sells=sellable,
        position_type=position_type,
    )

class EquityPositionReconciliationPolicyTests(
    unittest.TestCase
):
    def test_matched_position_is_marked_reconciled(
        self,
    ) -> None:
        local = make_local_state()
        broker = make_broker_position()

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=local,
            broker_position=broker,
            issues=frozenset(),
        )

        decision = (
            decide_equity_position_reconciliation(
                outcome
            )
        )

        self.assertEqual(
            decision.action,
            EquityPositionReconciliationAction
            .MARK_RECONCILED,
        )

    def test_quantity_mismatch_requires_reconciliation(
        self,
    ) -> None:
        local = make_local_state()
        broker = make_broker_position(
            quantity=Decimal("0.5"),
            sellable=Decimal("0.5"),
        )

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=local,
            broker_position=broker,
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .QUANTITY_MISMATCH,
                }
            ),
        )

        decision = (
            decide_equity_position_reconciliation(
                outcome
            )
        )

        self.assertEqual(
            decision.action,
            EquityPositionReconciliationAction
            .REQUIRE_RECONCILIATION,
        )

    def test_missing_broker_position_requires_reconciliation(
        self,
    ) -> None:
        local = make_local_state()

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=local,
            broker_position=None,
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .BROKER_POSITION_MISSING,
                }
            ),
        )

        decision = (
            decide_equity_position_reconciliation(
                outcome
            )
        )

        self.assertEqual(
            decision.action,
            EquityPositionReconciliationAction
            .REQUIRE_RECONCILIATION,
        )

    def test_broker_only_position_requires_review(
        self,
    ) -> None:
        broker = make_broker_position()

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=None,
            broker_position=broker,
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .LOCAL_POSITION_MISSING,
                }
            ),
        )

        decision = (
            decide_equity_position_reconciliation(
                outcome
            )
        )

        self.assertEqual(
            decision.action,
            EquityPositionReconciliationAction
            .BROKER_ONLY_REVIEW,
        )

    def test_multiple_issues_still_require_reconciliation(
        self,
    ) -> None:
        local = make_local_state()
        broker = make_broker_position(
            quantity=Decimal("0.75"),
            sellable=Decimal("0.25"),
        )

        outcome = EquityPositionReconciliationOutcome(
            symbol="AAPL",
            local_state=local,
            broker_position=broker,
            issues=frozenset(
                {
                    EquityPositionReconciliationIssue
                    .QUANTITY_MISMATCH,
                    EquityPositionReconciliationIssue
                    .SELLABILITY_RESTRICTED,
                }
            ),
        )

        decision = (
            decide_equity_position_reconciliation(
                outcome
            )
        )

        self.assertEqual(
            decision.action,
            EquityPositionReconciliationAction
            .REQUIRE_RECONCILIATION,
        )