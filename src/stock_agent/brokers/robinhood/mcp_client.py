from collections.abc import Callable
from typing import Any
from datetime import datetime, timezone

from stock_agent.brokers.robinhood.client import (
    RobinhoodOrderReceipt,
)
from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvocationUncertainError,
    MCPToolInvoker,
)
from stock_agent.brokers.robinhood.mcp_mapping import (
    build_robinhood_mcp_place_call,
    build_robinhood_mcp_review_call,
)
from stock_agent.brokers.robinhood.mcp_review_decoder import (
    decode_robinhood_mcp_review,
)
from stock_agent.brokers.robinhood.reviews import (
    RobinhoodOrderReview,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)
from stock_agent.brokers.robinhood.errors import (
    RobinhoodOrderNotReviewedError,
    RobinhoodPlacementUncertainError,
)
from stock_agent.brokers.robinhood.reconciliation import (
    build_placement_reconciliation_request,
)


ReviewDecoder = Callable[
    [RobinhoodExitSubmission, Any],
    RobinhoodOrderReview,
]

ReceiptDecoder = Callable[
    [RobinhoodExitSubmission, Any],
    RobinhoodOrderReceipt,
]


class MCPRobinhoodBrokerClient:
    def __init__(
        self,
        invoker: MCPToolInvoker,
        review_decoder: ReviewDecoder | None = None,
        receipt_decoder: ReceiptDecoder | None = None,
        placement_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._invoker = invoker

        self._review_decoder = (
            review_decoder
            or decode_robinhood_mcp_review
        )

        self._receipt_decoder = receipt_decoder

        self._approved_submissions: dict[
            str,
            RobinhoodExitSubmission,
        ] = {}

    def review_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReview:
        call = build_robinhood_mcp_review_call(
            submission
        )

        raw_result = self._invoker.call_tool(
            call.tool_name,
            call.arguments,
        )

        review = self._review_decoder(
            submission,
            raw_result,
        )

        # Never leave behind a stale approval for the same
        # logical order.
        self._approved_submissions.pop(
            submission.ref_id,
            None,
        )

        if (
            review.approved
            and review.submission == submission
        ):
            self._approved_submissions[
                submission.ref_id
            ] = submission

        return review

    def submit_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReceipt:
        if self._receipt_decoder is None:
            raise RuntimeError(
                "Robinhood MCP receipt decoder is not configured"
            )

        approved_submission = (
            self._approved_submissions.get(
                submission.ref_id
            )
        )

        if approved_submission != submission:
            raise RobinhoodOrderNotReviewedError(
                "exact Robinhood submission has not been approved by review"
            )

        call = build_robinhood_mcp_place_call(
            submission
        )

        placement_attempted_at = (
            self._placement_clock()
        )

        if (
            placement_attempted_at.tzinfo is None
            or placement_attempted_at.utcoffset() is None
        ):
            raise ValueError(
                "placement clock must return timezone-aware datetime"
            )

        reconciliation_request = (
            build_placement_reconciliation_request(
                submission,
                placement_attempted_at=placement_attempted_at,
            )
        )

        self._approved_submissions.pop(
            submission.ref_id
        )

        try:
            raw_result = self._invoker.call_tool(
                call.tool_name,
                call.arguments,
            )
        except MCPToolInvocationUncertainError as exc:
            raise RobinhoodPlacementUncertainError(
                reconciliation_request
            ) from exc

        try:
            return self._receipt_decoder(
                submission,
                raw_result,
            )
        except Exception as exc:
            raise RobinhoodPlacementUncertainError(
                reconciliation_request
            ) from exc