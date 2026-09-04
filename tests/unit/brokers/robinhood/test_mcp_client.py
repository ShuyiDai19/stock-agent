import unittest
from decimal import Decimal
from typing import Any
from datetime import datetime, timezone
from dataclasses import replace

from stock_agent.brokers.robinhood import (
    MCPRobinhoodBrokerClient,
    RobinhoodExitAction,
    RobinhoodExitOrderRequest,
    RobinhoodExitSubmission,
    RobinhoodOrderReview,
    RobinhoodOrderType,
    RobinhoodOrderReceipt,
    RobinhoodMCPReceiptDecoder,
    RobinhoodOrderNotReviewedError,
    MCPToolInvocationUncertainError,
    RobinhoodPlacementUncertainError,
)
from stock_agent.domain import AssetType

class FakeReceiptDecoder:
    def __init__(
        self,
        receipt: RobinhoodOrderReceipt,
    ) -> None:
        self.receipt = receipt

        self.call_count = 0
        self.received_submission = None
        self.received_raw_result = None

    def __call__(
        self,
        submission: RobinhoodExitSubmission,
        raw_result: Any,
    ) -> RobinhoodOrderReceipt:
        self.call_count += 1
        self.received_submission = submission
        self.received_raw_result = raw_result

        return self.receipt

class FakeMCPToolInvoker:
    def __init__(
        self,
        *,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

        self.call_count = 0
        self.received_tool_name = None
        self.received_arguments = None

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.call_count += 1
        self.received_tool_name = tool_name
        self.received_arguments = arguments

        if self.error is not None:
            raise self.error

        return self.result

class SequencedFakeMCPToolInvoker:
    def __init__(
        self,
        results: list[Any],
    ) -> None:
        self.results = list(results)

        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append(
            (
                tool_name,
                arguments,
            )
        )

        if not self.results:
            raise RuntimeError(
                "fake MCP result sequence exhausted"
            )

        result = self.results.pop(0)

        if isinstance(result, Exception):
            raise result

        return result

class FakeReviewDecoder:
    def __init__(
        self,
        *,
        approved: bool = True,
    ) -> None:
        self.approved = approved

        self.call_count = 0
        self.received_submission = None
        self.received_raw_result = None

    def __call__(
        self,
        submission: RobinhoodExitSubmission,
        raw_result: Any,
    ) -> RobinhoodOrderReview:
        self.call_count += 1
        self.received_submission = submission
        self.received_raw_result = raw_result

        return RobinhoodOrderReview(
            submission=submission,
            approved=self.approved,
        )

class FailingReceiptDecoder:
    def __init__(
        self,
        error: Exception,
    ) -> None:
        self.error = error
        self.call_count = 0

    def __call__(
        self,
        submission: RobinhoodExitSubmission,
        raw_result: Any,
    ) -> RobinhoodOrderReceipt:
        self.call_count += 1
        raise self.error


class MCPRobinhoodBrokerClientTests(unittest.TestCase):
    REF_ID = (
        "123e4567-e89b-12d3-a456-426614174000"
    )

    PLACEMENT_ATTEMPTED_AT = datetime(
        2026,
        9,
        3,
        8,
        0,
        tzinfo=timezone.utc,
    )

    def make_equity_submission(
        self,
    ) -> RobinhoodExitSubmission:
        request = RobinhoodExitOrderRequest(
            position_id="account-0000:equity:AAPL:order-123",
            account_number="account-0000",
            asset_type=AssetType.EQUITY,
            symbol="AAPL",
            quantity=Decimal("0.031"),
            action=RobinhoodExitAction.EQUITY_SELL,
            option_id=None,
        )

        return RobinhoodExitSubmission(
            request=request,
            ref_id=self.REF_ID,
            order_type=RobinhoodOrderType.MARKET,
        )

    def test_reviews_equity_exit_through_mcp_invoker(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        raw_result = {
            "order_checks": [],
            "preview": "fake review result",
        }

        invoker = FakeMCPToolInvoker(
            result=raw_result,
        )

        decoder = FakeReviewDecoder(
            approved=True,
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            decoder,
        )

        review = client.review_exit_order(
            submission
        )

        self.assertEqual(
            invoker.call_count,
            1,
        )

        self.assertEqual(
            invoker.received_tool_name,
            "review_equity_order",
        )

        self.assertEqual(
            invoker.received_arguments,
            {
                "account_number": "account-0000",
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
            },
        )

        self.assertEqual(
            decoder.call_count,
            1,
        )

        self.assertEqual(
            decoder.received_submission,
            submission,
        )

        self.assertEqual(
            decoder.received_raw_result,
            raw_result,
        )

        self.assertTrue(
            review.approved,
        )

        self.assertEqual(
            review.submission,
            submission,
        )

    def test_propagates_mcp_review_error(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = FakeMCPToolInvoker(
            error=RuntimeError(
                "MCP review failed"
            ),
        )

        decoder = FakeReviewDecoder()

        client = MCPRobinhoodBrokerClient(
            invoker,
            decoder,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "MCP review failed",
        ):
            client.review_exit_order(
                submission
            )

        self.assertEqual(
            invoker.call_count,
            1,
        )

        self.assertEqual(
            decoder.call_count,
            0,
        )


    def test_uses_default_review_decoder(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        raw_result = {
            "data": {
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "order_checks": {},
                "quote_data": {
                    "bid_price": "316.94",
                    "ask_price": "320.26",
                },
                "market_data_disclosure": (
                    "fake disclosure"
                ),
            }
        }

        invoker = FakeMCPToolInvoker(
            result=raw_result,
        )

        client = MCPRobinhoodBrokerClient(
            invoker
        )

        review = client.review_exit_order(
            submission
        )

        self.assertEqual(
            invoker.call_count,
            1,
        )

        self.assertEqual(
            invoker.received_tool_name,
            "review_equity_order",
        )

        self.assertTrue(
            review.approved,
        )

        self.assertEqual(
            review.submission,
            submission,
        )

        self.assertEqual(
            review.alerts,
            (),
        )

    def test_default_decoder_rejects_review_with_order_checks(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = FakeMCPToolInvoker(
            result={
                "data": {
                    "symbol": "AAPL",
                    "side": "sell",
                    "type": "market",
                    "quantity": "0.031",
                    "order_checks": {
                        "example_check": {
                            "detail": "order not permitted"
                        }
                    },
                }
            },
        )

        client = MCPRobinhoodBrokerClient(
            invoker
        )

        review = client.review_exit_order(
            submission
        )

        self.assertFalse(
            review.approved,
        )

        self.assertEqual(
            len(review.alerts),
            1,
        )

        self.assertIn(
            "order not permitted",
            review.alerts[0],
        )

    def test_submits_equity_exit_through_mcp_invoker(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        review_raw_result = {
            "data": {
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "order_checks": {},
            }
        }

        place_raw_result = {
            "fake": "place result",
        }

        receipt = RobinhoodOrderReceipt(
            broker_order_id="broker-order-123",
            submitted_at=datetime(
                2026,
                8,
                29,
                1,
                30,
                tzinfo=timezone.utc,
            ),
        )

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                review_raw_result,
                place_raw_result,
            ],
        )

        decoder = FakeReceiptDecoder(
            receipt
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=decoder,
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        result = client.submit_exit_order(
            submission
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        review_tool_name, review_arguments = (
            invoker.calls[0]
        )

        place_tool_name, place_arguments = (
            invoker.calls[1]
        )

        self.assertEqual(
            review_tool_name,
            "review_equity_order",
        )

        self.assertEqual(
            review_arguments,
            {
                "account_number": "account-0000",
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
            },
        )

        self.assertEqual(
            place_tool_name,
            "place_equity_order",
        )

        self.assertEqual(
            place_arguments,
            {
                "account_number": "account-0000",
                "symbol": "AAPL",
                "side": "sell",
                "type": "market",
                "quantity": "0.031",
                "time_in_force": "gfd",
                "market_hours": "regular_hours",
                "ref_id": self.REF_ID,
            },
        )

        self.assertEqual(
            decoder.call_count,
            1,
        )

        self.assertEqual(
            decoder.received_submission,
            submission,
        )

        self.assertEqual(
            decoder.received_raw_result,
            place_raw_result,
        )

        self.assertEqual(
            result,
            receipt,
        )

    def test_propagates_mcp_place_error(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
                RuntimeError(
                    "MCP place failed"
                ),
            ]
        )

        receipt_decoder = RobinhoodMCPReceiptDecoder(
            clock=lambda: datetime.now(
                timezone.utc
            ),
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=receipt_decoder,
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "MCP place failed",
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertEqual(
            invoker.calls[0][0],
            "review_equity_order",
        )

        self.assertEqual(
            invoker.calls[1][0],
            "place_equity_order",
        )
        with self.assertRaisesRegex(
            RobinhoodOrderNotReviewedError,
            "has not been approved by review",
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_does_not_invoke_place_without_receipt_decoder(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = FakeMCPToolInvoker()

        client = MCPRobinhoodBrokerClient(
            invoker
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "receipt decoder is not configured",
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            invoker.call_count,
            0,
        )

    def test_reviews_then_places_same_equity_submission(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        acknowledged_at = datetime(
            2026,
            8,
            29,
            7,
            30,
            tzinfo=timezone.utc,
        )

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "symbol": "AAPL",
                        "side": "sell",
                        "type": "market",
                        "quantity": "0.031",
                        "order_checks": {},
                        "quote_data": {
                            "bid_price": "316.94",
                            "ask_price": "320.26",
                        },
                        "market_data_disclosure": (
                            "fake disclosure"
                        ),
                    }
                },
                {
                    "data": {
                        "order": {
                            "id": "broker-order-123",
                            "state": "queued",
                            "quantity": "0.031",
                            "ref_id": self.REF_ID,
                        }
                    }
                },
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: acknowledged_at,
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        self.assertEqual(
            review.submission,
            submission,
        )

        receipt = client.submit_exit_order(
            submission
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        review_tool_name, review_arguments = (
            invoker.calls[0]
        )

        place_tool_name, place_arguments = (
            invoker.calls[1]
        )

        self.assertEqual(
            review_tool_name,
            "review_equity_order",
        )

        self.assertEqual(
            place_tool_name,
            "place_equity_order",
        )

        self.assertNotIn(
            "ref_id",
            review_arguments,
        )

        self.assertEqual(
            place_arguments["ref_id"],
            self.REF_ID,
        )

        place_without_ref_id = dict(
            place_arguments
        )

        place_without_ref_id.pop(
            "ref_id"
        )

        self.assertEqual(
            place_without_ref_id,
            review_arguments,
        )

        self.assertEqual(
            receipt.broker_order_id,
            "broker-order-123",
        )

        self.assertEqual(
            receipt.submitted_at,
            acknowledged_at,
        )

    def test_marks_wrong_place_response_ref_id_as_uncertain(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
                {
                    "data": {
                        "order": {
                            "id": "broker-order-123",
                            "ref_id": (
                                "123e4567-e89b-12d3-a456-426614174999"
                            ),
                        }
                    }
                },
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        with self.assertRaises(
            RobinhoodPlacementUncertainError
        ) as context:
            client.submit_exit_order(
                submission
            )

        error = context.exception

        self.assertEqual(
            error.position_id,
            submission.request.position_id,
        )

        self.assertEqual(
            error.ref_id,
            submission.ref_id,
        )

        self.assertIsInstance(
            error.__cause__,
            ValueError,
        )

        self.assertEqual(
            str(error.__cause__),
            (
                "Robinhood placement ref_id "
                "does not match submission"
            ),
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertEqual(
            invoker.calls[0][0],
            "review_equity_order",
        )

        self.assertEqual(
            invoker.calls[1][0],
            "place_equity_order",
        )

        with self.assertRaises(
            RobinhoodOrderNotReviewedError
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_does_not_place_without_approved_review(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
        )

        with self.assertRaisesRegex(
            RobinhoodOrderNotReviewedError,
            "has not been approved by review",
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            len(invoker.calls),
            0,
        )

    def test_does_not_place_after_rejected_review(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {
                            "example_check": {
                                "detail": (
                                    "order not permitted"
                                )
                            }
                        }
                    }
                },
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertFalse(
            review.approved,
        )

        with self.assertRaisesRegex(
            RobinhoodOrderNotReviewedError,
            "has not been approved by review",
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

        self.assertEqual(
            invoker.calls[0][0],
            "review_equity_order",
        )

    def test_does_not_place_modified_submission_after_review(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        modified_request = replace(
            submission.request,
            quantity=Decimal("0.032"),
        )

        modified_submission = replace(
            submission,
            request=modified_request,
        )

        # Same ref_id, different executable order.
        self.assertEqual(
            modified_submission.ref_id,
            submission.ref_id,
        )

        with self.assertRaisesRegex(
            RobinhoodOrderNotReviewedError,
            "has not been approved by review",
        ):
            client.submit_exit_order(
                modified_submission
            )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

    def test_does_not_place_when_placement_clock_is_naive(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
            placement_clock=lambda: datetime(
                2026,
                9,
                3,
                8,
                0,
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        with self.assertRaisesRegex(
            ValueError,
            (
                "placement clock must return "
                "timezone-aware datetime"
            ),
        ):
            client.submit_exit_order(
                submission
            )

        self.assertEqual(
            len(invoker.calls),
            1,
        )

        self.assertEqual(
            invoker.calls[0][0],
            "review_equity_order",
        )

    def test_marks_transport_failure_as_uncertain(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
                MCPToolInvocationUncertainError(
                    "MCP response timed out"
                ),
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
            placement_clock=lambda: (
                self.PLACEMENT_ATTEMPTED_AT
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        with self.assertRaises(
            RobinhoodPlacementUncertainError
        ) as context:
            client.submit_exit_order(
                submission
            )

        error = context.exception

        request = error.reconciliation_request

        self.assertEqual(
            request.position_id,
            submission.request.position_id,
        )

        self.assertEqual(
            request.account_number,
            submission.request.account_number,
        )

        self.assertEqual(
            request.asset_type,
            AssetType.EQUITY,
        )

        self.assertEqual(
            request.symbol,
            "AAPL",
        )

        self.assertEqual(
            request.ref_id,
            submission.ref_id,
        )

        self.assertEqual(
            request.placement_attempted_at,
            self.PLACEMENT_ATTEMPTED_AT,
        )

        self.assertIsNone(
            request.option_id,
        )

        self.assertEqual(
            error.position_id,
            submission.request.position_id,
        )

        self.assertEqual(
            error.ref_id,
            submission.ref_id,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

        self.assertIsInstance(
            error.__cause__,
            MCPToolInvocationUncertainError,
        )

    def test_marks_receipt_decode_failure_as_uncertain(
        self,
    ) -> None:
        submission = self.make_equity_submission()

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
                {
                    "data": {
                        "unexpected": "response"
                    }
                },
            ]
        )

        decoder = FailingReceiptDecoder(
            ValueError(
                "invalid placement receipt"
            )
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=decoder,
            placement_clock=lambda: (
                self.PLACEMENT_ATTEMPTED_AT
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        with self.assertRaises(
            RobinhoodPlacementUncertainError
        ) as context:
            client.submit_exit_order(
                submission
            )

        error = context.exception

        request = error.reconciliation_request

        self.assertEqual(
            request.position_id,
            submission.request.position_id,
        )

        self.assertEqual(
            request.account_number,
            submission.request.account_number,
        )

        self.assertEqual(
            request.ref_id,
            submission.ref_id,
        )

        self.assertEqual(
            request.placement_attempted_at,
            self.PLACEMENT_ATTEMPTED_AT,
        )

        self.assertEqual(
            error.position_id,
            submission.request.position_id,
        )

        self.assertEqual(
            error.ref_id,
            submission.ref_id,
        )

        self.assertIsInstance(
            error.__cause__,
            ValueError,
        )

        self.assertEqual(
            decoder.call_count,
            1,
        )

        self.assertEqual(
            len(invoker.calls),
            2,
        )

    def test_option_uncertainty_preserves_option_id(
        self,
    ) -> None:
        request = RobinhoodExitOrderRequest(
            position_id="account-0000:option:AAPL:order-456",
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

        invoker = SequencedFakeMCPToolInvoker(
            results=[
                {
                    "data": {
                        "order_checks": {},
                    }
                },
                MCPToolInvocationUncertainError(
                    "MCP response timed out"
                ),
            ]
        )

        client = MCPRobinhoodBrokerClient(
            invoker,
            receipt_decoder=RobinhoodMCPReceiptDecoder(
                clock=lambda: datetime.now(
                    timezone.utc
                ),
            ),
        )

        review = client.review_exit_order(
            submission
        )

        self.assertTrue(
            review.approved,
        )

        with self.assertRaises(
            RobinhoodPlacementUncertainError
        ) as context:
            client.submit_exit_order(
                submission
            )

        reconciliation = (
            context.exception.reconciliation_request
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

if __name__ == "__main__":
    unittest.main()