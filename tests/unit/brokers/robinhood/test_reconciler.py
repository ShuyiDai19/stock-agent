
import unittest
from datetime import datetime, timedelta, timezone

from stock_agent.brokers.robinhood import (
    PlacementReconciliationRequest,
    PlacementReconciliationStatus,
    RobinhoodOrderLookupResult,
    RobinhoodOrderLookupStatus,
    RobinhoodPlacementReconciler,
)
from stock_agent.domain import AssetType


class FakeRobinhoodOrderLookup:
    def __init__(
        self,
        result: RobinhoodOrderLookupResult,
    ) -> None:
        self.result = result
        self.call_count = 0
        self.received_request = None

    def lookup(
        self,
        request: PlacementReconciliationRequest,
    ) -> RobinhoodOrderLookupResult:
        self.call_count += 1
        self.received_request = request
        return self.result


class RobinhoodPlacementReconcilerTests(unittest.TestCase):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    PLACEMENT_ATTEMPTED_AT = datetime(
        2026,
        9,
        2,
        4,
        40,
        tzinfo=timezone.utc,
    )

    GRACE_PERIOD = timedelta(seconds=30)

    def make_request(
        self,
    ) -> PlacementReconciliationRequest:
        return PlacementReconciliationRequest(
            position_id="position-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            ref_id=self.REF_ID,
            placement_attempted_at=(
                self.PLACEMENT_ATTEMPTED_AT
            ),
            option_id=None,
        )

    def test_returns_found_outcome(
        self,
    ) -> None:
        request = self.make_request()

        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.FOUND,
                broker_order_id="broker-order-123",
            )
        )

        checked_at = datetime(
            2026,
            9,
            2,
            4,
            45,
            tzinfo=timezone.utc,
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: checked_at,
            not_found_grace_period=self.GRACE_PERIOD,
        )

        outcome = reconciler.reconcile(request)

        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(lookup.received_request, request)
        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.FOUND,
        )
        self.assertEqual(
            outcome.broker_order_id,
            "broker-order-123",
        )
        self.assertEqual(outcome.checked_at, checked_at)
        self.assertEqual(
            outcome.request.placement_attempted_at,
            self.PLACEMENT_ATTEMPTED_AT,
        )

    def test_returns_not_found_after_grace_period(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
            )
        )

        checked_at = datetime(
            2026,
            9,
            2,
            4,
            41,
            tzinfo=timezone.utc,
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: checked_at,
            not_found_grace_period=self.GRACE_PERIOD,
        )

        outcome = reconciler.reconcile(
            self.make_request()
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.NOT_FOUND,
        )
        self.assertIsNone(outcome.broker_order_id)

    def test_keeps_not_found_unknown_within_grace_period(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
            )
        )

        checked_at = datetime(
            2026,
            9,
            2,
            4,
            40,
            20,
            tzinfo=timezone.utc,
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: checked_at,
            not_found_grace_period=self.GRACE_PERIOD,
        )

        outcome = reconciler.reconcile(
            self.make_request()
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.STILL_UNKNOWN,
        )
        self.assertIsNone(outcome.broker_order_id)
        self.assertIn(
            "within placement reconciliation grace period",
            outcome.message,
        )

    def test_returns_not_found_at_grace_period_boundary(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
            )
        )

        checked_at = datetime(
            2026,
            9,
            2,
            4,
            40,
            30,
            tzinfo=timezone.utc,
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: checked_at,
            not_found_grace_period=self.GRACE_PERIOD,
        )

        outcome = reconciler.reconcile(
            self.make_request()
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.NOT_FOUND,
        )

    def test_returns_still_unknown_outcome(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.UNKNOWN,
                message="broker query unavailable",
            )
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: datetime.now(timezone.utc),
            not_found_grace_period=self.GRACE_PERIOD,
        )

        outcome = reconciler.reconcile(
            self.make_request()
        )

        self.assertEqual(
            outcome.status,
            PlacementReconciliationStatus.STILL_UNKNOWN,
        )
        self.assertEqual(
            outcome.message,
            "broker query unavailable",
        )

    def test_rejects_naive_clock_result(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
            )
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: datetime(
                2026,
                9,
                2,
                4,
                45,
            ),
            not_found_grace_period=self.GRACE_PERIOD,
        )

        with self.assertRaisesRegex(
            ValueError,
            (
                "reconciliation clock must return "
                "timezone-aware datetime"
            ),
        ):
            reconciler.reconcile(self.make_request())

    def test_rejects_check_before_placement_attempt(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
            )
        )

        checked_at = datetime(
            2026,
            9,
            2,
            4,
            39,
            59,
            tzinfo=timezone.utc,
        )

        reconciler = RobinhoodPlacementReconciler(
            lookup,
            clock=lambda: checked_at,
            not_found_grace_period=self.GRACE_PERIOD,
        )

        with self.assertRaisesRegex(
            ValueError,
            (
                "reconciliation check cannot precede "
                "placement attempt"
            ),
        ):
            reconciler.reconcile(self.make_request())

    def test_rejects_negative_not_found_grace_period(
        self,
    ) -> None:
        lookup = FakeRobinhoodOrderLookup(
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "not_found_grace_period cannot be negative",
        ):
            RobinhoodPlacementReconciler(
                lookup,
                clock=lambda: datetime.now(timezone.utc),
                not_found_grace_period=timedelta(
                    seconds=-1
                ),
            )

    def test_found_lookup_requires_broker_order_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "found lookup requires broker_order_id",
        ):
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.FOUND,
            )

    def test_not_found_lookup_rejects_broker_order_id(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            (
                "non-found lookup cannot contain "
                "broker_order_id"
            ),
        ):
            RobinhoodOrderLookupResult(
                status=RobinhoodOrderLookupStatus.NOT_FOUND,
                broker_order_id="broker-order-123",
            )


if __name__ == "__main__":
    unittest.main()