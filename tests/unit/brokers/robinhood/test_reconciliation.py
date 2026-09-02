import unittest
from decimal import Decimal
from datetime import datetime, timezone

from stock_agent.brokers.robinhood import (
    PlacementReconciliationRequest,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
    build_placement_reconciliation_request,
    PlacementReconciliationOutcome,
    PlacementReconciliationStatus,
)
from stock_agent.domain import AssetType


class PlacementReconciliationRequestTests(
    unittest.TestCase
):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    def test_builds_equity_reconciliation_request(
        self,
    ) -> None:
        request = RobinhoodExitOrderRequest(
            position_id=(
                "account-0000:equity:AAPL:order-123"
            ),
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

        reconciliation = (
            build_placement_reconciliation_request(
                submission
            )
        )

        self.assertEqual(
            reconciliation.position_id,
            request.position_id,
        )

        self.assertEqual(
            reconciliation.account_number,
            "account-0000",
        )

        self.assertEqual(
            reconciliation.asset_type,
            AssetType.EQUITY,
        )

        self.assertEqual(
            reconciliation.symbol,
            "AAPL",
        )

        self.assertEqual(
            reconciliation.ref_id,
            self.REF_ID,
        )

        self.assertIsNone(
            reconciliation.option_id,
        )

    def test_builds_option_reconciliation_request(
        self,
    ) -> None:
        request = RobinhoodExitOrderRequest(
            position_id=(
                "account-0000:option:AAPL:order-456"
            ),
            account_number="account-0000",
            asset_type=AssetType.OPTION,
            symbol="AAPL",
            quantity=Decimal("1"),
            action=(
                RobinhoodExitAction.OPTION_SELL_TO_CLOSE
            ),
            option_id="option-contract-123",
        )

        submission = RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.LIMIT,
            limit_price=Decimal("2.40"),
        )

        reconciliation = (
            build_placement_reconciliation_request(
                submission
            )
        )

        self.assertEqual(
            reconciliation.asset_type,
            AssetType.OPTION,
        )

        self.assertEqual(
            reconciliation.option_id,
            "option-contract-123",
        )

        self.assertEqual(
            reconciliation.ref_id,
            self.REF_ID,
        )

    def test_option_reconciliation_requires_option_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "option reconciliation requires option_id",
        ):
            PlacementReconciliationRequest(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.OPTION,
                symbol="AAPL",
                ref_id=self.REF_ID,
                option_id=None,
            )

    def test_equity_reconciliation_rejects_option_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            (
                "equity reconciliation cannot contain "
                "option_id"
            ),
        ):
            PlacementReconciliationRequest(
                position_id="position-123",
                account_number="account-0000",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                ref_id=self.REF_ID,
                option_id="option-contract-123",
            )

class PlacementReconciliationOutcomeTests(
    unittest.TestCase
):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    def make_request(
        self,
    ) -> PlacementReconciliationRequest:
        return PlacementReconciliationRequest(
            position_id="position-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            ref_id=self.REF_ID,
            option_id=None,
        )

    def test_creates_found_outcome(
        self,
    ) -> None:
        checked_at = datetime(
            2026,
            9,
            2,
            4,
            30,
            tzinfo=timezone.utc,
        )

        outcome = PlacementReconciliationOutcome(
            request=self.make_request(),
            status=PlacementReconciliationStatus.FOUND,
            checked_at=checked_at,
            broker_order_id="broker-order-123",
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.FOUND,
        )

        self.assertEqual(
            outcome.broker_order_id,
            "broker-order-123",
        )

        self.assertEqual(
            outcome.checked_at,
            checked_at,
        )

    def test_creates_not_found_outcome(
        self,
    ) -> None:
        outcome = PlacementReconciliationOutcome(
            request=self.make_request(),
            status=PlacementReconciliationStatus.NOT_FOUND,
            checked_at=datetime.now(
                timezone.utc
            ),
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.NOT_FOUND,
        )

        self.assertIsNone(
            outcome.broker_order_id,
        )

    def test_creates_still_unknown_outcome(
        self,
    ) -> None:
        outcome = PlacementReconciliationOutcome(
            request=self.make_request(),
            status=(
                PlacementReconciliationStatus.STILL_UNKNOWN
            ),
            checked_at=datetime.now(
                timezone.utc
            ),
            message="broker query unavailable",
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.STILL_UNKNOWN,
        )

        self.assertEqual(
            outcome.message,
            "broker query unavailable",
        )

    def test_found_requires_broker_order_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "found reconciliation requires broker_order_id",
        ):
            PlacementReconciliationOutcome(
                request=self.make_request(),
                status=(
                    PlacementReconciliationStatus.FOUND
                ),
                checked_at=datetime.now(
                    timezone.utc
                ),
            )

    def test_not_found_rejects_broker_order_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            (
                "non-found reconciliation cannot contain "
                "broker_order_id"
            ),
        ):
            PlacementReconciliationOutcome(
                request=self.make_request(),
                status=(
                    PlacementReconciliationStatus.NOT_FOUND
                ),
                checked_at=datetime.now(
                    timezone.utc
                ),
                broker_order_id="broker-order-123",
            )

    def test_rejects_naive_checked_at(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "checked_at must be timezone-aware",
        ):
            PlacementReconciliationOutcome(
                request=self.make_request(),
                status=(
                    PlacementReconciliationStatus.NOT_FOUND
                ),
                checked_at=datetime(
                    2026,
                    9,
                    2,
                    4,
                    30,
                ),
            )


if __name__ == "__main__":
    unittest.main()