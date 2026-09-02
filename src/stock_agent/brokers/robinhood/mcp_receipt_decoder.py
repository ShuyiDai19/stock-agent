from collections.abc import Callable
from datetime import datetime
from typing import Any

from stock_agent.brokers.robinhood.client import (
    RobinhoodOrderReceipt,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)


class RobinhoodMCPReceiptDecoder:
    def __init__(
        self,
        clock: Callable[[], datetime],
    ) -> None:
        self._clock = clock

    def __call__(
        self,
        submission: RobinhoodExitSubmission,
        raw_result: Any,
    ) -> RobinhoodOrderReceipt:
        if not isinstance(raw_result, dict):
            raise ValueError(
                "Robinhood placement result must be a mapping"
            )

        data = raw_result.get("data")

        if not isinstance(data, dict):
            raise ValueError(
                "Robinhood placement result must contain data"
            )

        order = data.get("order")

        if not isinstance(order, dict):
            raise ValueError(
                "Robinhood placement result must contain order"
            )

        broker_order_id = order.get("id")

        if (
            not isinstance(broker_order_id, str)
            or not broker_order_id.strip()
        ):
            raise ValueError(
                "Robinhood placement result must contain order id"
            )

        returned_ref_id = order.get("ref_id")

        if returned_ref_id != submission.ref_id:
            raise ValueError(
                "Robinhood placement ref_id does not match submission"
            )

        submitted_at = self._clock()

        if (
            submitted_at.tzinfo is None
            or submitted_at.utcoffset() is None
        ):
            raise ValueError(
                "receipt clock must return timezone-aware datetime"
            )

        return RobinhoodOrderReceipt(
            broker_order_id=broker_order_id,
            submitted_at=submitted_at,
        )