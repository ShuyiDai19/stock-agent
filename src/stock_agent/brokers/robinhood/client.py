from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)

from stock_agent.brokers.robinhood.reviews import (
    RobinhoodOrderReview,
)


@dataclass(frozen=True)
class RobinhoodOrderReceipt:
    broker_order_id: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not self.broker_order_id.strip():
            raise ValueError(
                "broker_order_id cannot be empty"
            )

        if (
            self.submitted_at.tzinfo is None
            or self.submitted_at.utcoffset() is None
        ):
            raise ValueError(
                "submitted_at must be timezone-aware"
            )


class RobinhoodBrokerClient(Protocol):
    def review_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReview:
        ...

    def submit_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReceipt:
        ...