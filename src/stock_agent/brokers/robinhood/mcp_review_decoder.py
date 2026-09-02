import json
from typing import Any

from stock_agent.brokers.robinhood.reviews import (
    RobinhoodOrderReview,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)


def decode_robinhood_mcp_review(
    submission: RobinhoodExitSubmission,
    raw_result: Any,
) -> RobinhoodOrderReview:
    if not isinstance(raw_result, dict):
        raise ValueError(
            "Robinhood review result must be a mapping"
        )

    data = raw_result.get("data")

    if not isinstance(data, dict):
        raise ValueError(
            "Robinhood review result must contain data"
        )

    order_checks = data.get("order_checks")

    if not isinstance(order_checks, dict):
        raise ValueError(
            "Robinhood review result must contain order_checks"
        )

    if not order_checks:
        return RobinhoodOrderReview(
            submission=submission,
            approved=True,
            alerts=(),
        )

    return RobinhoodOrderReview(
        submission=submission,
        approved=False,
        alerts=(
            json.dumps(
                order_checks,
                sort_keys=True,
            ),
        ),
    )