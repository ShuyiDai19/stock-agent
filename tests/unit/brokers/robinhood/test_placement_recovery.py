import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    PlacementRecoveryAction,
    PlacementRecoveryPlanner,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAcknowledgement,
    PlacementAttemptRecord,
    PlacementAttemptStatus,
)
from stock_agent.domain import AssetType


class PlacementRecoveryPlannerTests(
    unittest.TestCase
):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    ATTEMPTED_AT = datetime(
        2026,
        9,
        2,
        4,
        40,
        tzinfo=timezone.utc,
    )

    def setUp(self) -> None:
        self.planner = PlacementRecoveryPlanner()

    def make_record(
        self,
        status: PlacementAttemptStatus,
    ) -> PlacementAttemptRecord:
        record = PlacementAttemptRecord(
            submission=RobinhoodExitSubmission(
                request=RobinhoodExitOrderRequest(
                    position_id="position-123",
                    account_number="account-0000",
                    asset_type=AssetType.EQUITY,
                    symbol="AAPL",
                    quantity=Decimal("0.031"),
                    action=RobinhoodExitAction.EQUITY_SELL,
                    option_id=None,
                ),
                ref_id=self.REF_ID,
                order_type=RobinhoodOrderType.MARKET,
            ),
            placement_attempted_at=self.ATTEMPTED_AT,
        )

        if status is PlacementAttemptStatus.ACKNOWLEDGED:
            return replace(
                record,
                status=status,
                acknowledgement=PlacementAcknowledgement(
                    broker_order_id="broker-order-123",
                    acknowledged_at=datetime(
                        2026,
                        9,
                        2,
                        4,
                        41,
                        tzinfo=timezone.utc,
                    ),
                ),
            )

        return replace(
            record,
            status=status,
        )

    def test_prepared_requires_reconciliation(
        self,
    ) -> None:
        plan = self.planner.plan(
            self.make_record(
                PlacementAttemptStatus.PREPARED
            )
        )

        self.assertEqual(
            plan.action,
            PlacementRecoveryAction.RECONCILE,
        )

    def test_submitting_requires_reconciliation(
        self,
    ) -> None:
        plan = self.planner.plan(
            self.make_record(
                PlacementAttemptStatus.SUBMITTING
            )
        )

        self.assertEqual(
            plan.action,
            PlacementRecoveryAction.RECONCILE,
        )

    def test_uncertain_requires_reconciliation(
        self,
    ) -> None:
        plan = self.planner.plan(
            self.make_record(
                PlacementAttemptStatus.UNCERTAIN
            )
        )

        self.assertEqual(
            plan.action,
            PlacementRecoveryAction.RECONCILE,
        )

    def test_not_sent_requires_fresh_review(
        self,
    ) -> None:
        record = self.make_record(
            PlacementAttemptStatus.NOT_SENT
        )

        plan = self.planner.plan(
            record
        )

        self.assertEqual(
            plan.action,
            PlacementRecoveryAction.FRESH_REVIEW_REQUIRED,
        )

        self.assertEqual(
            plan.record,
            record,
        )

    def test_acknowledged_requires_no_action(
        self,
    ) -> None:
        plan = self.planner.plan(
            self.make_record(
                PlacementAttemptStatus.ACKNOWLEDGED
            )
        )

        self.assertEqual(
            plan.action,
            PlacementRecoveryAction.NO_ACTION,
        )