from stock_agent.brokers.robinhood.client import (
    RobinhoodBrokerClient,
    RobinhoodOrderReceipt,
)
from stock_agent.brokers.robinhood.errors import (
    LiveExecutionDisabledError,
)
from stock_agent.brokers.robinhood.submissions import (
    RobinhoodExitSubmission,
)
from stock_agent.brokers.robinhood.reviews import (
    RobinhoodOrderReview,
)


class GuardedRobinhoodBrokerClient:
    def __init__(
        self,
        client: RobinhoodBrokerClient,
        *,
        live_enabled: bool,
    ) -> None:
        if not isinstance(live_enabled, bool):
            raise TypeError(
                "live_enabled must be a bool"
            )

        self._client = client
        self._live_enabled = live_enabled

    def submit_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReceipt:
        if not self._live_enabled:
            raise LiveExecutionDisabledError(
                "live Robinhood execution is disabled"
            )

        return self._client.submit_exit_order(
            submission
        )

    def review_exit_order(
        self,
        submission: RobinhoodExitSubmission,
    ) -> RobinhoodOrderReview:
        return self._client.review_exit_order(
            submission
        )