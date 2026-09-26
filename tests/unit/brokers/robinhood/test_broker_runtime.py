import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from typing import cast
from datetime import datetime, timedelta, timezone

from stock_agent.brokers.robinhood.broker_runtime import (
    open_robinhood_broker,
    open_robinhood_broker_from_env,
    resolve_live_execution_enabled,
    build_production_placement_journal,
    resolve_placement_journal_path,
    run_robinhood_startup_recovery,
    RobinhoodStartupRecoverySummary,
    open_robinhood_runtime,
    build_production_entry_placement_journal,
    build_production_position_state_store,
    resolve_entry_placement_journal_path,
    resolve_position_state_path,
)
from stock_agent.brokers.robinhood.errors import (
    LiveExecutionDisabledError,
)
from stock_agent.brokers.robinhood.placement_journal import (
    PlacementAttemptStatus,
    SQLitePlacementAttemptJournal,
    PlacementAttemptJournal,
    PlacementAttemptRecord,
)
from decimal import Decimal
from uuid import uuid4

from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
    RobinhoodMarketHours,
    RobinhoodOrderType,
    RobinhoodTimeInForce,
)
from stock_agent.domain import AssetType
from stock_agent.brokers.robinhood.entry_preflight_reader import (
    RobinhoodEquityEntryPreflightReader,
)
from stock_agent.brokers.robinhood.equity_exit_reconciler import (
    RobinhoodEquityExitReconciler,
)
from stock_agent.brokers.robinhood.mcp_quote_provider import (
    MCPRobinhoodEquityQuoteProvider,
)
from stock_agent.brokers.robinhood.equity_exit_price_provider import (
    RobinhoodEquityExitPriceProvider,
)


    
class FakeCallToolResult:
    def __init__(
        self,
        structured_content,
        *,
        is_error: bool = False,
    ) -> None:
        self.structured_content = structured_content
        self.is_error = is_error

class LifecycleCheckingFakeMCPClient:
    def __init__(
        self,
        server,
        *,
        journal,
    ) -> None:
        self.server = server
        self.journal = journal
        self.calls = []

    async def __aenter__(
        self,
    ):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return None

    async def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        if tool_name == "review_equity_order":
            return FakeCallToolResult(
                {
                    "data": {
                        "order_checks": {},
                    }
                }
            )

        if tool_name == "place_equity_order":
            ref_id = arguments["ref_id"]

            persisted = self.journal.get(
                ref_id
            )

            if persisted is None:
                raise AssertionError(
                    "placement attempt was not "
                    "persisted before place"
                )

            if (
                persisted.status
                is not PlacementAttemptStatus.SUBMITTING
            ):
                raise AssertionError(
                    "placement attempt must be "
                    "SUBMITTING before place"
                )

            return FakeCallToolResult(
                {
                    "data": {
                        "order": {
                            "id": "broker-order-123",
                            "ref_id": ref_id,
                        }
                    }
                }
            )

        raise AssertionError(
            f"unexpected MCP tool: {tool_name}"
        )

class FakeMCPClient:
    def __init__(
        self,
        server,
    ) -> None:
        self.server = server
        self.calls = []

    async def __aenter__(
        self,
    ):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return None

    async def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        raise AssertionError(
            "MCP tool must not be called "
            "while live execution is disabled"
        )

class NoCallFakeInvoker:
    def __init__(
        self,
    ) -> None:
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        raise AssertionError(
            "MCP must not be called "
            "when there are no unresolved "
            "placement attempts"
        )

class RecoveryFailingFakeMCPClient:
    def __init__(
        self,
        server,
    ) -> None:
        self.server = server
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return None

    async def call_tool(
        self,
        tool_name,
        arguments,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
            )
        )

        raise RuntimeError(
            "simulated reconciliation failure"
        )

class RobinhoodBrokerRuntimeTests(
    unittest.TestCase
):
    def make_submission(
        self,
    ) -> RobinhoodExitSubmission:
        return RobinhoodExitSubmission(
            request=RobinhoodExitOrderRequest(
                position_id="position-123",
                account_number="agentic-account",
                asset_type=AssetType.EQUITY,
                symbol="AAPL",
                quantity=Decimal("0.001"),
                action=RobinhoodExitAction.EQUITY_SELL,
                option_id=None,
            ),
            ref_id=(
                "123e4567-e89b-12d3-a456-426614174000"
            ),
            order_type=RobinhoodOrderType.MARKET,
            time_in_force=RobinhoodTimeInForce.GFD,
            market_hours=RobinhoodMarketHours.REGULAR_HOURS,
            limit_price=None,
        )

    def test_live_execution_is_disabled_by_default(
        self,
    ) -> None:
        clients = []

        def factory(server):
            client = FakeMCPClient(server)
            clients.append(client)
            return client

        with tempfile.TemporaryDirectory() as directory:
            journal = (
                SQLitePlacementAttemptJournal(
                    Path(directory)
                    / "placement.sqlite3"
                )
            )
            journal.initialize()

            with open_robinhood_broker(
                account_number=(
                    "agentic-account"
                ),
                placement_journal=journal,
                client_factory=factory,
            ) as broker:
                with self.assertRaises(
                    LiveExecutionDisabledError
                ):
                    broker.submit_exit_order(
                        self.make_submission()
                    )

            self.assertEqual(
                len(clients),
                1,
            )

            self.assertEqual(
                clients[0].calls,
                [],
            )

    def test_rejects_non_boolean_live_enabled(
        self,
    ) -> None:
        dummy_journal = cast(
            PlacementAttemptJournal,
            object(),
        )

        with self.assertRaisesRegex(
            TypeError,
            "live_enabled must be a bool",
        ):
            with open_robinhood_broker(
                account_number="agentic-account",
                placement_journal=dummy_journal,
                live_enabled="false",
            ):
                pass

    def test_live_execution_defaults_to_disabled(
        self,
    ) -> None:
        self.assertFalse(
            resolve_live_execution_enabled({})
        )


    def test_live_execution_explicit_false_is_disabled(
        self,
    ) -> None:
        self.assertFalse(
            resolve_live_execution_enabled(
                {
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "false",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                }
            )
        )


    def test_live_execution_requires_live_runtime_mode(
        self,
    ) -> None:
        self.assertTrue(
            resolve_live_execution_enabled(
                {
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                }
            )
        )


    def test_invalid_live_execution_value_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            resolve_live_execution_enabled(
                {
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "yes",
                }
            )


    def test_invalid_live_setting_fails_before_mcp_start(
        self,
    ) -> None:
        factory_called = False

        def factory(server):
            nonlocal factory_called
            factory_called = True

            raise AssertionError(
                "MCP connection must not start"
            )

        with self.assertRaises(
            ValueError
        ):
            with open_robinhood_broker_from_env(
                account_number="agentic-account",
                placement_journal=object(),
                env={
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "yes",
                },
                client_factory=factory,
            ):
                pass

        self.assertFalse(
            factory_called
        )

    def test_live_true_preserves_full_safe_execution_lifecycle(
        self,
    ) -> None:
        submission = self.make_submission()

        with tempfile.TemporaryDirectory() as directory:
            journal = SQLitePlacementAttemptJournal(
                Path(directory)
                / "placement.sqlite3"
            )
            journal.initialize()

            clients = []

            def factory(server):
                client = LifecycleCheckingFakeMCPClient(
                    server,
                    journal=journal,
                )

                clients.append(
                    client
                )

                return client

            with open_robinhood_broker_from_env(
                account_number="agentic-account",
                placement_journal=journal,
                env={
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                },
                client_factory=factory,
            ) as broker:
                review = broker.review_exit_order(
                    submission
                )

                self.assertTrue(
                    review.approved
                )

                receipt = broker.submit_exit_order(
                    submission
                )

            self.assertEqual(
                len(clients),
                1,
            )

            self.assertEqual(
                [
                    tool_name
                    for tool_name, _ in clients[0].calls
                ],
                [
                    "review_equity_order",
                    "place_equity_order",
                ],
            )

            review_arguments = (
                clients[0].calls[0][1]
            )

            place_arguments = (
                clients[0].calls[1][1]
            )

            self.assertEqual(
                review_arguments[
                    "account_number"
                ],
                "agentic-account",
            )

            self.assertEqual(
                place_arguments[
                    "account_number"
                ],
                "agentic-account",
            )

            self.assertEqual(
                place_arguments["ref_id"],
                submission.ref_id,
            )

            self.assertEqual(
                receipt.broker_order_id,
                "broker-order-123",
            )

            persisted = journal.get(
                submission.ref_id
            )

            self.assertIsNotNone(
                persisted
            )

            self.assertEqual(
                persisted.status,
                PlacementAttemptStatus.ACKNOWLEDGED,
            )

            self.assertIsNotNone(
                persisted.acknowledgement
            )

            self.assertEqual(
                persisted
                .acknowledgement
                .broker_order_id,
                "broker-order-123",
            )

            self.assertNotIn(
                "ref_id",
                review_arguments,
            )

            self.assertEqual(
                place_arguments["ref_id"],
                submission.ref_id,
            )

    def test_live_flag_alone_is_not_enough(
        self,
    ) -> None:
        self.assertFalse(
            resolve_live_execution_enabled(
                {
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                }
            )
        )


    def test_live_runtime_mode_alone_is_not_enough(
        self,
    ) -> None:
        self.assertFalse(
            resolve_live_execution_enabled(
                {
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                }
            )
        )


    def test_safe_runtime_mode_keeps_live_disabled(
        self,
    ) -> None:
        self.assertFalse(
            resolve_live_execution_enabled(
                {
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "safe",
                }
            )
        )


    def test_invalid_runtime_mode_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "STOCK_AGENT_RUNTIME_MODE",
        ):
            resolve_live_execution_enabled(
                {
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "production",
                }
            )

    def test_startup_safety_summary_is_explicit_and_redacted(
        self,
    ) -> None:
        account_number = (
            "secret-agentic-account-123456"
        )

        clients = []

        def factory(server):
            client = FakeMCPClient(
                server
            )
            clients.append(
                client
            )
            return client

        dummy_journal = cast(
            PlacementAttemptJournal,
            object(),
        )

        with self.assertLogs(
            "stock_agent.brokers.robinhood.broker_runtime",
            level="WARNING",
        ) as captured:
            with open_robinhood_broker_from_env(
                account_number=account_number,
                placement_journal=dummy_journal,
                env={},
                client_factory=factory,
            ):
                pass

        output = "\n".join(
            captured.output
        )

        self.assertIn(
            "runtime_mode=safe",
            output,
        )

        self.assertIn(
            "live_execution=DISABLED",
            output,
        )

        self.assertIn(
            "account_guard=ENABLED",
            output,
        )

        self.assertNotIn(
            account_number,
            output,
        )

    def test_default_placement_journal_path(
        self,
    ) -> None:
        base_dir = Path("/project")

        self.assertEqual(
            resolve_placement_journal_path(
                {},
                base_dir=base_dir,
            ),
            (
                base_dir
                / ".state"
                / "robinhood"
                / "placement.sqlite3"
            ),
        )

    def test_explicit_placement_journal_path(
        self,
    ) -> None:
        base_dir = Path("/project")

        self.assertEqual(
            resolve_placement_journal_path(
                {
                    "ROBINHOOD_PLACEMENT_JOURNAL_PATH":
                        "runtime/orders.sqlite3",
                },
                base_dir=base_dir,
            ),
            (
                base_dir
                / "runtime"
                / "orders.sqlite3"
            ),
        )

    def test_empty_placement_journal_path_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ROBINHOOD_PLACEMENT_JOURNAL_PATH",
        ):
            resolve_placement_journal_path(
                {
                    "ROBINHOOD_PLACEMENT_JOURNAL_PATH":
                        "   ",
                }
            )

    def test_build_production_placement_journal_initializes_database(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)

            journal = (
                build_production_placement_journal(
                    {},
                    base_dir=base_dir,
                )
            )

            expected_path = (
                base_dir
                / ".state"
                / "robinhood"
                / "placement.sqlite3"
            )

            self.assertTrue(
                expected_path.exists()
            )

            self.assertEqual(
                journal.list_unresolved(),
                [],
            )

    # def test_runtime_allows_live_when_recovery_is_clean(
    #     self,
    # ) -> None:
    #     with tempfile.TemporaryDirectory() as directory:
    #         journal = (
    #             SQLitePlacementAttemptJournal(
    #                 Path(directory)
    #                 / "placement.sqlite3"
    #             )
    #         )
    #         journal.initialize()

    #         clients = []

    #         def factory(server):
    #             client = FakeMCPClient(
    #                 server
    #             )
    #             clients.append(client)
    #             return client

    #         with open_robinhood_runtime(
    #             account_number="agentic-account",
    #             placement_journal=journal,
    #             not_found_grace_period=(
    #                 timedelta(0)
    #             ),
    #             env={
    #                 "ROBINHOOD_LIVE_EXECUTION_ENABLED":
    #                     "true",
    #                 "STOCK_AGENT_RUNTIME_MODE":
    #                     "live",
    #             },
    #             client_factory=factory,
    #         ) as runtime:
    #             self.assertTrue(
    #                 runtime
    #                 .live_execution_requested
    #             )

    #             self.assertTrue(
    #                 runtime
    #                 .live_execution_enabled
    #             )

    #             self.assertEqual(
    #                 runtime
    #                 .recovery
    #                 .unresolved_attempt_count,
    #                 0,
    #             )

    # def test_runtime_blocks_live_when_recovery_remains_unresolved(
    #     self,
    # ) -> None:
    #     submission = self.make_submission()

    #     with tempfile.TemporaryDirectory() as directory:
    #         journal = (
    #             SQLitePlacementAttemptJournal(
    #                 Path(directory)
    #                 / "placement.sqlite3"
    #             )
    #         )
    #         journal.initialize()

    #         journal.insert(
    #             PlacementAttemptRecord(
    #                 submission=submission,
    #                 attempted_at=datetime.now(
    #                     timezone.utc
    #                 ),
    #                 status=(
    #                     PlacementAttemptStatus
    #                     .PREPARED
    #                 ),
    #             )
    #         )

    #         def factory(server):
    #             return (
    #                 RecoveryFailingFakeMCPClient(
    #                     server
    #                 )
    #             )

    #         with open_robinhood_runtime(
    #             account_number="agentic-account",
    #             placement_journal=journal,
    #             not_found_grace_period=(
    #                 timedelta(0)
    #             ),
    #             env={
    #                 "ROBINHOOD_LIVE_EXECUTION_ENABLED":
    #                     "true",
    #                 "STOCK_AGENT_RUNTIME_MODE":
    #                     "live",
    #             },
    #             client_factory=factory,
    #         ) as runtime:
    #             self.assertTrue(
    #                 runtime
    #                 .live_execution_requested
    #             )

    #             self.assertFalse(
    #                 runtime
    #                 .live_execution_enabled
    #             )

    #             self.assertEqual(
    #                 runtime
    #                 .recovery
    #                 .unresolved_attempt_count,
    #                 1,
    #             )

    #             with self.assertRaises(
    #                 LiveExecutionDisabledError
    #             ):
    #                 runtime.broker.submit_exit_order(
    #                     submission
    #                 )

    def test_startup_recovery_is_clean_when_journal_is_empty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = (
                SQLitePlacementAttemptJournal(
                    Path(directory)
                    / "placement.sqlite3"
                )
            )
            journal.initialize()

            invoker = NoCallFakeInvoker()

            summary = (
                run_robinhood_startup_recovery(
                    invoker=invoker,
                    placement_journal=journal,
                    not_found_grace_period=(
                        timedelta(0)
                    ),
                )
            )

            self.assertEqual(
                summary.results,
                (),
            )

            self.assertEqual(
                summary.unresolved_attempt_count,
                0,
            )

            self.assertFalse(
                summary.has_unresolved_attempts
            )

            self.assertEqual(
                invoker.calls,
                [],
            )

    def test_runtime_allows_live_when_recovery_is_clean(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = (
                SQLitePlacementAttemptJournal(
                    Path(directory)
                    / "placement.sqlite3"
                )
            )
            journal.initialize()

            clients = []

            def factory(server):
                client = FakeMCPClient(
                    server
                )
                clients.append(
                    client
                )
                return client

            with open_robinhood_runtime(
                account_number="agentic-account",
                placement_journal=journal,
                not_found_grace_period=(
                    timedelta(0)
                ),
                env={
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                },
                client_factory=factory,
            ) as runtime:
                self.assertTrue(
                    runtime.live_execution_requested
                )

                self.assertTrue(
                    runtime.live_execution_enabled
                )

                self.assertEqual(
                    runtime.recovery
                    .unresolved_attempt_count,
                    0,
                )

                self.assertFalse(
                    runtime.recovery
                    .has_unresolved_attempts
                )

                self.assertIs(
                    runtime.placement_journal,
                    journal,
                )

                self.assertIsInstance(
                    runtime.entry_preflight_reader,
                    RobinhoodEquityEntryPreflightReader,
                )

            self.assertEqual(
                len(clients),
                1,
            )

            self.assertEqual(
                clients[0].calls,
                [],
            )

    def test_runtime_blocks_live_when_recovery_is_unresolved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = (
                SQLitePlacementAttemptJournal(
                    Path(directory)
                    / "placement.sqlite3"
                )
            )
            journal.initialize()

            clients = []

            def factory(server):
                client = FakeMCPClient(
                    server
                )
                clients.append(
                    client
                )
                return client

            recovery_summary = (
                RobinhoodStartupRecoverySummary(
                    results=(),
                    unresolved_attempt_count=1,
                )
            )

            with patch(
                (
                    "stock_agent.brokers.robinhood."
                    "broker_runtime."
                    "run_robinhood_startup_recovery"
                ),
                return_value=recovery_summary,
            ):
                with self.assertLogs(
                    (
                        "stock_agent.brokers."
                        "robinhood.broker_runtime"
                    ),
                    level="WARNING",
                ) as captured:
                    with open_robinhood_runtime(
                        account_number=(
                            "agentic-account"
                        ),
                        placement_journal=journal,
                        not_found_grace_period=(
                            timedelta(0)
                        ),
                        env={
                            (
                                "ROBINHOOD_"
                                "LIVE_EXECUTION_ENABLED"
                            ):
                                "true",
                            "STOCK_AGENT_RUNTIME_MODE":
                                "live",
                        },
                        client_factory=factory,
                    ) as runtime:
                        self.assertTrue(
                            runtime
                            .live_execution_requested
                        )

                        self.assertFalse(
                            runtime
                            .live_execution_enabled
                        )

                        self.assertTrue(
                            runtime.recovery
                            .has_unresolved_attempts
                        )

                        with self.assertRaises(
                            LiveExecutionDisabledError
                        ):
                            runtime.broker.submit_exit_order(
                                self.make_submission()
                            )

                        self.assertIsInstance(
                            runtime.entry_preflight_reader,
                            RobinhoodEquityEntryPreflightReader,
                        )

            output = "\n".join(
                captured.output
            )

            self.assertIn(
                "live execution BLOCKED",
                output,
            )

            self.assertEqual(
                clients[0].calls,
                [],
            )

    def test_default_entry_placement_journal_path(
        self,
    ) -> None:
        base_dir = Path("/project")

        self.assertEqual(
            resolve_entry_placement_journal_path(
                {},
                base_dir=base_dir,
            ),
            (
                base_dir
                / ".state"
                / "robinhood"
                / "entry-placement.sqlite3"
            ),
        )

    def test_default_position_state_path(
        self,
    ) -> None:
        base_dir = Path("/project")

        self.assertEqual(
            resolve_position_state_path(
                {},
                base_dir=base_dir,
            ),
            (
                base_dir
                / ".state"
                / "robinhood"
                / "positions.sqlite3"
            ),
        )

    def test_build_production_entry_placement_journal_initializes_database(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)

            journal = (
                build_production_entry_placement_journal(
                    {},
                    base_dir=base_dir,
                )
            )

            expected_path = (
                base_dir
                / ".state"
                / "robinhood"
                / "entry-placement.sqlite3"
            )

            self.assertTrue(
                expected_path.exists()
            )

            self.assertEqual(
                journal.list_uncertain(
                    account_number="agentic-account"
                ),
                [],
            )

    def test_build_production_position_state_store_initializes_database(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)

            store = (
                build_production_position_state_store(
                    {},
                    base_dir=base_dir,
                )
            )

            expected_path = (
                base_dir
                / ".state"
                / "robinhood"
                / "positions.sqlite3"
            )

            self.assertTrue(
                expected_path.exists()
            )

            self.assertEqual(
                store.list_by_status(
                    account_number=(
                        "agentic-account"
                    ),
                    statuses=(),
                ),
                [],
            )

    def test_empty_entry_placement_journal_path_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH",
        ):
            resolve_entry_placement_journal_path(
                {
                    "ROBINHOOD_ENTRY_PLACEMENT_JOURNAL_PATH":
                        "   ",
                }
            )

    def test_empty_position_state_path_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ROBINHOOD_POSITION_STATE_PATH",
        ):
            resolve_position_state_path(
                {
                    "ROBINHOOD_POSITION_STATE_PATH":
                        "   ",
                }
            )

    def test_runtime_builds_entry_components_in_safe_mode(
        self,
    ) -> None:
        clients = []

        def factory(server):
            client = FakeMCPClient(
                server
            )
            clients.append(client)
            return client

        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)

            with open_robinhood_runtime(
                account_number=(
                    "agentic-account"
                ),
                not_found_grace_period=(
                    timedelta(0)
                ),
                env={},
                base_dir=base_dir,
                client_factory=factory,
            ) as runtime:
                self.assertIsNotNone(
                    runtime.entry_placement_journal
                )

                self.assertIsNotNone(
                    runtime.position_store
                )

                self.assertIsNotNone(
                    runtime.entry_recovery_service
                )

                self.assertIsNotNone(
                    runtime.entry_activation_reconciler
                )

                # Critical safety invariant:
                # safe runtime exposes no live placer.
                self.assertIsNone(
                    runtime.entry_placer
                )

                self.assertFalse(
                    runtime.live_execution_enabled
                )

                self.assertIsInstance(
                    runtime.entry_preflight_reader,
                    RobinhoodEquityEntryPreflightReader,
                )

            self.assertTrue(
                (
                    base_dir
                    / ".state"
                    / "robinhood"
                    / "entry-placement.sqlite3"
                ).exists()
            )

            self.assertTrue(
                (
                    base_dir
                    / ".state"
                    / "robinhood"
                    / "positions.sqlite3"
                ).exists()
            )

    def test_runtime_exposes_entry_placer_when_live_is_enabled(
        self,
    ) -> None:
        def factory(server):
            return FakeMCPClient(
                server
            )

        with tempfile.TemporaryDirectory() as directory:
            with open_robinhood_runtime(
                account_number=(
                    "agentic-account"
                ),
                not_found_grace_period=(
                    timedelta(0)
                ),
                env={
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "true",
                    "STOCK_AGENT_RUNTIME_MODE":
                        "live",
                },
                base_dir=Path(directory),
                client_factory=factory,
            ) as runtime:
                self.assertTrue(
                    runtime.live_execution_requested
                )

                self.assertTrue(
                    runtime.live_execution_enabled
                )

                self.assertIsNotNone(
                    runtime.entry_placer
                )

                self.assertEqual(
                    runtime.account_number,
                    "agentic-account",
                )

                self.assertIsInstance(
                    runtime.entry_preflight_reader,
                    RobinhoodEquityEntryPreflightReader,
                )

    def test_runtime_does_not_expose_entry_placer_when_exit_recovery_is_unresolved(
        self,
    ) -> None:
        clients = []

        def factory(server):
            client = FakeMCPClient(
                server
            )
            clients.append(
                client
            )
            return client

        recovery_summary = (
            RobinhoodStartupRecoverySummary(
                results=(),
                unresolved_attempt_count=1,
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "stock_agent.brokers.robinhood."
                "broker_runtime."
                "run_robinhood_startup_recovery",
                return_value=recovery_summary,
            ):
                with open_robinhood_runtime(
                    account_number=(
                        "agentic-account"
                    ),
                    not_found_grace_period=(
                        timedelta(0)
                    ),
                    env={
                        "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                            "true",
                        "STOCK_AGENT_RUNTIME_MODE":
                            "live",
                    },
                    base_dir=Path(directory),
                    client_factory=factory,
                ) as runtime:
                    # User explicitly requested LIVE.
                    self.assertTrue(
                        runtime.live_execution_requested
                    )

                    # But unresolved exit placement
                    # prevents live execution.
                    self.assertFalse(
                        runtime.live_execution_enabled
                    )

                    self.assertIsNone(
                        runtime.entry_placer
                    )

                    self.assertIsNotNone(
                        runtime.entry_recovery_service
                    )

                    self.assertIsNotNone(
                        runtime.entry_activation_reconciler
                    )

                    self.assertIsNotNone(
                        runtime.entry_placement_journal
                    )

                    self.assertIsNotNone(
                        runtime.position_store
                    )
                    self.assertEqual(
                        runtime.account_number,
                        "agentic-account",
                    )

                    self.assertIsInstance(
                        runtime.entry_preflight_reader,
                        RobinhoodEquityEntryPreflightReader,
                    )

    def test_runtime_exposes_equity_exit_reconciler_without_running_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clients = []

            def client_factory(
                server,
            ):
                client = FakeMCPClient(
                    server
                )
                clients.append(
                    client
                )
                return client

            with open_robinhood_runtime(
                account_number=(
                    "agentic-account"
                ),
                not_found_grace_period=(
                    timedelta(seconds=120)
                ),
                env={
                    "STOCK_AGENT_RUNTIME_MODE":
                        "safe",
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "false",
                },
                base_dir=Path(
                    directory
                ),
                client_factory=(
                    client_factory
                ),
            ) as runtime:
                self.assertIsInstance(
                    runtime.equity_exit_reconciler,
                    RobinhoodEquityExitReconciler,
                )

                self.assertFalse(
                    runtime.live_execution_enabled
                )

            self.assertEqual(
                len(clients),
                1,
            )

            # Merely constructing the runtime must
            # not perform exit close-confirmation reads.
            self.assertEqual(
                clients[0].calls,
                [],
            )

            self.assertIsInstance(
                runtime.equity_quote_provider,
                MCPRobinhoodEquityQuoteProvider,
            )

            self.assertIsInstance(
                runtime.equity_exit_price_provider,
                RobinhoodEquityExitPriceProvider,
            )

    def test_runtime_exit_reconciliation_with_no_closing_positions_is_clean(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clients = []

            def client_factory(
                server,
            ):
                client = FakeMCPClient(
                    server
                )
                clients.append(
                    client
                )
                return client

            with open_robinhood_runtime(
                account_number=(
                    "agentic-account"
                ),
                not_found_grace_period=(
                    timedelta(seconds=120)
                ),
                env={
                    "STOCK_AGENT_RUNTIME_MODE":
                        "safe",
                    "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                        "false",
                },
                base_dir=Path(
                    directory
                ),
                client_factory=(
                    client_factory
                ),
            ) as runtime:
                result = (
                    runtime
                    .equity_exit_reconciler
                    .reconcile(
                        account_number=(
                            "agentic-account"
                        )
                    )
                )

                self.assertEqual(
                    result,
                    (),
                )

            self.assertEqual(
                len(clients),
                1,
            )

            # No CLOSING positions means no
            # get_equity_orders call is necessary.
            self.assertEqual(
                clients[0].calls,
                [],
            )