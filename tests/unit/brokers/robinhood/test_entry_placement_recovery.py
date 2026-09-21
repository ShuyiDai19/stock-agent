import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from stock_agent.brokers.robinhood.entry_placement import (
    EntryPlacementStatus,
    EquityEntryPlacementRecord,
    SQLiteEquityEntryPlacementJournal,
)
from stock_agent.brokers.robinhood.entry_placement_recovery import (
    EquityEntryPlacementRecoveryService,
)
from stock_agent.brokers.robinhood.reconciler import (
    RobinhoodOrderLookupResult,
    RobinhoodOrderLookupStatus,
)


_REF_ID = (
    "123e4567-e89b-12d3-a456-426614174000"
)

_ATTEMPTED_AT = datetime(
    2026,
    9,
    21,
    12,
    0,
    tzinfo=timezone.utc,
)

_CHECKED_AT = datetime(
    2026,
    9,
    21,
    12,
    1,
    tzinfo=timezone.utc,
)


class FakeLookup:
    def __init__(
        self,
        result: RobinhoodOrderLookupResult,
    ) -> None:
        self.result = result
        self.requests = []

    def lookup(
        self,
        request,
    ) -> RobinhoodOrderLookupResult:
        self.requests.append(request)
        return self.result


class FailingLookup:
    def lookup(
        self,
        request,
    ):
        raise RuntimeError(
            "broker lookup failed"
        )


class EquityEntryPlacementRecoveryServiceTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temp_dir = (
            tempfile.TemporaryDirectory()
        )

        self.journal = (
            SQLiteEquityEntryPlacementJournal(
                Path(self.temp_dir.name)
                / "entry.sqlite3"
            )
        )

        self.journal.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def insert_uncertain(
        self,
    ) -> None:
        self.journal.insert(
            EquityEntryPlacementRecord(
                ref_id=_REF_ID,
                account_number=(
                    "agentic-account"
                ),
                symbol="AAPL",
                arguments={
                    "symbol": "AAPL",
                },
                attempted_at=_ATTEMPTED_AT,
                status=(
                    EntryPlacementStatus
                    .UNCERTAIN
                ),
            )
        )

    def test_found_order_recovers_as_acknowledged(
        self,
    ) -> None:
        self.insert_uncertain()

        lookup = FakeLookup(
            RobinhoodOrderLookupResult(
                status=(
                    RobinhoodOrderLookupStatus
                    .FOUND
                ),
                broker_order_id=(
                    "broker-order-1"
                ),
            )
        )

        service = (
            EquityEntryPlacementRecoveryService(
                self.journal,
                lookup,
                clock=lambda: _CHECKED_AT,
            )
        )

        results = service.recover(
            account_number=(
                "agentic-account"
            )
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertTrue(
            results[0].recovered
        )

        persisted = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            persisted.status,
            EntryPlacementStatus
            .ACKNOWLEDGED,
        )

        self.assertEqual(
            persisted.broker_order_id,
            "broker-order-1",
        )

        self.assertEqual(
            persisted.recovered_at,
            _CHECKED_AT,
        )

    def test_not_found_remains_uncertain(
        self,
    ) -> None:
        self.insert_uncertain()

        service = (
            EquityEntryPlacementRecoveryService(
                self.journal,
                FakeLookup(
                    RobinhoodOrderLookupResult(
                        status=(
                            RobinhoodOrderLookupStatus
                            .NOT_FOUND
                        )
                    )
                ),
                clock=lambda: _CHECKED_AT,
            )
        )

        results = service.recover(
            account_number=(
                "agentic-account"
            )
        )

        self.assertFalse(
            results[0].recovered
        )

        persisted = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            persisted.status,
            EntryPlacementStatus
            .UNCERTAIN,
        )

        self.assertIsNone(
            persisted.broker_order_id
        )

    def test_unknown_remains_uncertain(
        self,
    ) -> None:
        self.insert_uncertain()

        service = (
            EquityEntryPlacementRecoveryService(
                self.journal,
                FakeLookup(
                    RobinhoodOrderLookupResult(
                        status=(
                            RobinhoodOrderLookupStatus
                            .UNKNOWN
                        ),
                        message=(
                            "lookup inconclusive"
                        ),
                    )
                ),
                clock=lambda: _CHECKED_AT,
            )
        )

        results = service.recover(
            account_number=(
                "agentic-account"
            )
        )

        self.assertFalse(
            results[0].recovered
        )

        persisted = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            persisted.status,
            EntryPlacementStatus
            .UNCERTAIN,
        )

    def test_lookup_failure_remains_uncertain(
        self,
    ) -> None:
        self.insert_uncertain()

        service = (
            EquityEntryPlacementRecoveryService(
                self.journal,
                FailingLookup(),
                clock=lambda: _CHECKED_AT,
            )
        )

        results = service.recover(
            account_number=(
                "agentic-account"
            )
        )

        self.assertIsInstance(
            results[0].error,
            RuntimeError,
        )

        persisted = self.journal.get(
            _REF_ID
        )

        self.assertEqual(
            persisted.status,
            EntryPlacementStatus
            .UNCERTAIN,
        )