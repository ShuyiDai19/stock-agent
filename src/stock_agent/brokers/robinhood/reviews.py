from dataclasses import dataclass

from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)


@dataclass(frozen=True)
class RobinhoodOrderReview:
    submission: RobinhoodExitSubmission
    approved: bool
    alerts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for alert in self.alerts:
            if not alert.strip():
                raise ValueError(
                    "review alerts cannot contain empty values"
                )