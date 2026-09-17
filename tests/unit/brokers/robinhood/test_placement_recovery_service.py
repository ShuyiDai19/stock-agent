import unittest
from datetime import datetime, timezone
from decimal import Decimal

from stock_agent.brokers.robinhood import (
    PlacementRecoveryAction,
    PlacementRecoveryPlanner,
    PlacementRecoveryService,
    PlacementReconciliationOutcome,
    PlacementReconciliationStatus,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderType,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptRecord,
    PlacementAttemptStatus,
    SQLitePlacementAttemptJournal,
)
from stock_agent.domain import AssetType


class FakeRecoveryJournal:
    def __init__(
        self,
        records: list[PlacementAttemptRecord],
    ) -> None:
        self.records = records
        self.list_call_count = 0
        self.observation_calls = []
        self.recovery_calls = []
        self.events = []

    def list_unresolved(
        self,
    ) -> list[PlacementAttemptRecord]:
        self.list_call_count += 1
        return list(self.records)

    def insert(self, record) -> None:
        raise AssertionError(
            "recovery service must not insert journal records"
        )

    def transition(
        self,
        *args,
        **kwargs,
    ) -> None:
        raise AssertionError(
            "recovery service must not transition journal state"
        )

    def acknowledge(
        self,
        *args,
        **kwargs,
    ) -> None:
        raise AssertionError(
            "recovery service must not acknowledge journal state"
        )

    def recover_found(
        self,
        ref_id,
        evidence,
    ) -> None:
        self.recovery_calls.append(
            (
                ref_id,
                evidence,
            )
        )

        self.events.append(
            (
                "recover_found",
                ref_id,
            )
        )

    def append_reconciliation_observation(
        self,
        observation,
    ) -> None:
        self.observation_calls.append(
            observation
        )

        self.events.append(
            (
                "append_observation",
                observation.ref_id,
            )
        )

class FakePlacementReconciler:
    def __init__(self) -> None:
        self.requests = []

    def reconcile(
        self,
        request,
    ) -> PlacementReconciliationOutcome:
        self.requests.append(request)

        return PlacementReconciliationOutcome(
            request=request,
            status=PlacementReconciliationStatus.STILL_UNKNOWN,
            checked_at=datetime(
                2026,
                9,
                11,
                2,
                30,
                tzinfo=timezone.utc,
            ),
            message="fake reconciliation result",
        )

class FailingRecoveryJournal(
    FakeRecoveryJournal
):
    def recover_found(
        self,
        ref_id,
        evidence,
    ) -> None:
        self.recovery_calls.append(
            (
                ref_id,
                evidence,
            )
        )

        self.events.append(
            (
                "recover_found",
                ref_id,
            )
        )

        raise RuntimeError(
            "recovery persistence failed"
        )

class PlacementRecoveryServiceTests(
    unittest.TestCase
):
    def make_record(
        self,
        *,
        ref_id: str,
        status: PlacementAttemptStatus,
        attempted_at: datetime,
    ) -> PlacementAttemptRecord:
        return PlacementAttemptRecord(
            submission=RobinhoodExitSubmission(
                request=RobinhoodExitOrderRequest(
                    position_id=f"position:{ref_id}",
                    account_number="account-0000",
                    asset_type=AssetType.EQUITY,
                    symbol="AAPL",
                    quantity=Decimal("0.031"),
                    action=RobinhoodExitAction.EQUITY_SELL,
                    option_id=None,
                ),
                ref_id=ref_id,
                order_type=RobinhoodOrderType.MARKET,
            ),
            placement_attempted_at=attempted_at,
            status=status,
        )

    def test_reconciles_all_unresolved_records(
        self,
    ) -> None:
        first = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174001"
            ),
            status=PlacementAttemptStatus.SUBMITTING,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                0,
                tzinfo=timezone.utc,
            ),
        )

        second = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174002"
            ),
            status=PlacementAttemptStatus.UNCERTAIN,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                1,
                tzinfo=timezone.utc,
            ),
        )

        journal = FakeRecoveryJournal(
            [first, second]
        )

        reconciler = FakePlacementReconciler()

        service = PlacementRecoveryService(
            journal,
            PlacementRecoveryPlanner(),
            reconciler,
        )

        results = service.recover()

        self.assertEqual(
            len(results),
            2,
        )

        self.assertEqual(
            journal.list_call_count,
            1,
        )

        self.assertEqual(
            len(reconciler.requests),
            2,
        )

        self.assertEqual(
            reconciler.requests[0].ref_id,
            first.submission.ref_id,
        )

        self.assertEqual(
            reconciler.requests[0].placement_attempted_at,
            first.placement_attempted_at,
        )

        self.assertEqual(
            results[0].plan.action,
            PlacementRecoveryAction.RECONCILE,
        )

        self.assertEqual(
            results[0].outcome.status,
            PlacementReconciliationStatus.STILL_UNKNOWN,
        )

        self.assertIsNone(
            results[0].error,
        )

        self.assertEqual(
            journal.recovery_calls,
            [],
        )

    def test_isolates_reconciliation_failure_per_record(
        self,
    ) -> None:
        first = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174001"
            ),
            status=PlacementAttemptStatus.SUBMITTING,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                0,
                tzinfo=timezone.utc,
            ),
        )

        second = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174002"
            ),
            status=PlacementAttemptStatus.UNCERTAIN,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                1,
                tzinfo=timezone.utc,
            ),
        )

        class FailingThenSuccessfulReconciler:
            def __init__(inner_self) -> None:
                inner_self.call_count = 0

            def reconcile(
                inner_self,
                request,
            ):
                inner_self.call_count += 1

                if inner_self.call_count == 1:
                    raise RuntimeError(
                        "broker lookup failed"
                    )

                return PlacementReconciliationOutcome(
                    request=request,
                    status=(
                        PlacementReconciliationStatus.STILL_UNKNOWN
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        11,
                        2,
                        30,
                        tzinfo=timezone.utc,
                    ),
                )

        reconciler = FailingThenSuccessfulReconciler()

        service = PlacementRecoveryService(
            FakeRecoveryJournal(
                [first, second]
            ),
            PlacementRecoveryPlanner(),
            reconciler,
        )

        results = service.recover()

        self.assertEqual(
            len(results),
            2,
        )

        self.assertIsInstance(
            results[0].error,
            RuntimeError,
        )

        self.assertIsNone(
            results[0].outcome,
        )

        self.assertIsNone(
            results[1].error,
        )

        self.assertEqual(
            results[1].outcome.status,
            PlacementReconciliationStatus.STILL_UNKNOWN,
        )

        self.assertEqual(
            reconciler.call_count,
            2,
        )

    def test_empty_journal_returns_no_recovery_results(
        self,
    ) -> None:
        journal = FakeRecoveryJournal([])

        reconciler = FakePlacementReconciler()

        service = PlacementRecoveryService(
            journal,
            PlacementRecoveryPlanner(),
            reconciler,
        )

        results = service.recover()

        self.assertEqual(
            results,
            [],
        )

        self.assertEqual(
            journal.list_call_count,
            1,
        )

        self.assertEqual(
            reconciler.requests,
            [],
        )

    def test_persists_recovered_evidence_for_found_order(
        self,
    ) -> None:
        record = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174001"
            ),
            status=PlacementAttemptStatus.SUBMITTING,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                0,
                tzinfo=timezone.utc,
            ),
        )

        recovered_at = datetime(
            2026,
            9,
            11,
            2,
            30,
            tzinfo=timezone.utc,
        )

        class FoundReconciler:
            def reconcile(
                self,
                request,
            ) -> PlacementReconciliationOutcome:
                return PlacementReconciliationOutcome(
                    request=request,
                    status=(
                        PlacementReconciliationStatus.FOUND
                    ),
                    checked_at=recovered_at,
                    broker_order_id="broker-order-123",
                )

        journal = FakeRecoveryJournal(
            [record]
        )

        service = PlacementRecoveryService(
            journal,
            PlacementRecoveryPlanner(),
            FoundReconciler(),
        )

        results = service.recover()

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0].outcome.status,
            PlacementReconciliationStatus.FOUND,
        )

        self.assertIsNone(
            results[0].error,
        )

        self.assertIsNone(
            results[0].persistence_error,
        )

        self.assertEqual(
            len(journal.recovery_calls),
            1,
        )

        ref_id, evidence = (
            journal.recovery_calls[0]
        )

        self.assertEqual(
            ref_id,
            record.submission.ref_id,
        )

        self.assertEqual(
            evidence.broker_order_id,
            "broker-order-123",
        )

        self.assertEqual(
            evidence.recovered_at,
            recovered_at,
        )

    def test_not_found_does_not_modify_journal(
        self,
    ) -> None:
        record = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174001"
            ),
            status=PlacementAttemptStatus.UNCERTAIN,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                0,
                tzinfo=timezone.utc,
            ),
        )

        class NotFoundReconciler:
            def reconcile(
                self,
                request,
            ) -> PlacementReconciliationOutcome:
                return PlacementReconciliationOutcome(
                    request=request,
                    status=(
                        PlacementReconciliationStatus.NOT_FOUND
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        11,
                        2,
                        30,
                        tzinfo=timezone.utc,
                    ),
                )

        journal = FakeRecoveryJournal(
            [record]
        )

        service = PlacementRecoveryService(
            journal,
            PlacementRecoveryPlanner(),
            NotFoundReconciler(),
        )

        results = service.recover()

        self.assertEqual(
            results[0].outcome.status,
            PlacementReconciliationStatus.NOT_FOUND,
        )

        self.assertEqual(
            journal.recovery_calls,
            [],
        )

    def test_preserves_found_outcome_when_recovery_persistence_fails(
        self,
    ) -> None:
        record = self.make_record(
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174001"
            ),
            status=PlacementAttemptStatus.SUBMITTING,
            attempted_at=datetime(
                2026,
                9,
                11,
                2,
                0,
                tzinfo=timezone.utc,
            ),
        )

        class FoundReconciler:
            def reconcile(
                self,
                request,
            ):
                return PlacementReconciliationOutcome(
                    request=request,
                    status=(
                        PlacementReconciliationStatus.FOUND
                    ),
                    checked_at=datetime(
                        2026,
                        9,
                        11,
                        2,
                        30,
                        tzinfo=timezone.utc,
                    ),
                    broker_order_id="broker-order-123",
                )

        journal = FailingRecoveryJournal(
            [record]
        )

        service = PlacementRecoveryService(
            journal,
            PlacementRecoveryPlanner(),
            FoundReconciler(),
        )

        results = service.recover()

        result = results[0]

        self.assertEqual(
            result.outcome.status,
            PlacementReconciliationStatus.FOUND,
        )

        self.assertEqual(
            result.outcome.broker_order_id,
            "broker-order-123",
        )

        self.assertIsNone(
            result.error,
        )

        self.assertIsInstance(
            result.persistence_error,
            RuntimeError,
        )

        self.assertEqual(
            str(result.persistence_error),
            "recovery persistence failed",
        )

    def test_found_recovery_persists_recovered_state(
        self,
    ) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            journal = SQLitePlacementAttemptJournal(
                Path(directory) / "placement.sqlite3"
            )

            journal.initialize()

            record = self.make_record(
                ref_id=(
                    "123e4567-e89b-12d3-a456-426614174001"
                ),
                status=PlacementAttemptStatus.PREPARED,
                attempted_at=datetime(
                    2026,
                    9,
                    11,
                    2,
                    0,
                    tzinfo=timezone.utc,
                ),
            )

            journal.insert(
                record
            )

            journal.transition(
                record.submission.ref_id,
                expected_status=(
                    PlacementAttemptStatus.PREPARED
                ),
                new_status=(
                    PlacementAttemptStatus.SUBMITTING
                ),
            )

            recovered_at = datetime(
                2026,
                9,
                11,
                2,
                30,
                tzinfo=timezone.utc,
            )

            class FoundReconciler:
                def reconcile(
                    self,
                    request,
                ):
                    return PlacementReconciliationOutcome(
                        request=request,
                        status=(
                            PlacementReconciliationStatus.FOUND
                        ),
                        checked_at=recovered_at,
                        broker_order_id="broker-order-123",
                    )

            service = PlacementRecoveryService(
                journal,
                PlacementRecoveryPlanner(),
                FoundReconciler(),
            )

            results = service.recover()

            self.assertEqual(
                results[0].outcome.status,
                PlacementReconciliationStatus.FOUND,
            )

            persisted = journal.get(
                record.submission.ref_id
            )

            self.assertEqual(
                persisted.status,
                PlacementAttemptStatus.RECOVERED,
            )

            self.assertEqual(
                persisted.recovery_evidence.broker_order_id,
                "broker-order-123",
            )

            self.assertEqual(
                persisted.recovery_evidence.recovered_at,
                recovered_at,
            )

            self.assertIsNone(
                persisted.acknowledgement,
            )