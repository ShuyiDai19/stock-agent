from collections.abc import Callable
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from stock_agent.market_data.freshness import (
    DEFAULT_MAX_QUOTE_AGE,
    require_fresh_quote_timestamp,
)
from stock_agent.brokers.robinhood.orders import (
    RobinhoodExitOrderRequest,
    build_robinhood_exit_order_request,
)
from stock_agent.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExitIntent,
)
from stock_agent.brokers.robinhood.client import (
    RobinhoodBrokerClient,
)
from stock_agent.brokers.robinhood.pricing import (
    RobinhoodExitPriceProvider,
    build_robinhood_exit_submission,
)
from stock_agent.brokers.robinhood.errors import (
    RobinhoodOrderReviewMismatchError,
    RobinhoodOrderReviewRejectedError,
)


class DryRunRobinhoodExitExecutor:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )
        self.last_request: RobinhoodExitOrderRequest | None = None

    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        request = build_robinhood_exit_order_request(
            intent
        )

        self.last_request = request

        return ExecutionResult(
            position_id=intent.position_id,
            status=ExecutionStatus.PREVIEWED,
            submitted_at=self._clock(),
            broker_order_id=None,
            message="Robinhood exit order previewed; no order submitted",
        )

class LiveRobinhoodExitExecutor:
    def __init__(
        self,
        client: RobinhoodBrokerClient,
        price_provider: RobinhoodExitPriceProvider,
        *,
        ref_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        max_quote_age: timedelta = (
            DEFAULT_MAX_QUOTE_AGE
        ),
    ) -> None:
        self._client = client
        self._price_provider = price_provider
        self._ref_id_factory = (
            ref_id_factory
            or (lambda: str(uuid4()))
        )
        self._clock = (
            clock
            or (
                lambda: datetime.now(
                    timezone.utc
                )
            )
        )
        self._max_quote_age = (
            max_quote_age
        )

        if (
            self._max_quote_age
            <= timedelta(0)
        ):
            raise ValueError(
                "max_quote_age must be positive"
            )


    def execute(
        self,
        intent: ExitIntent,
    ) -> ExecutionResult:
        request = build_robinhood_exit_order_request(
            intent
        )

        quote = self._price_provider.get_exit_price(
            request
        )

        require_fresh_quote_timestamp(
            observed_at=quote.observed_at,
            evaluated_at=self._clock(),
            max_quote_age=self._max_quote_age,
        )

        ref_id = self._ref_id_factory()

        submission = build_robinhood_exit_submission(
            request,
            quote,
            ref_id=ref_id,
        )

        review = self._client.review_exit_order(
            submission
        )

        if review.submission != submission:
            raise RobinhoodOrderReviewMismatchError(
                "reviewed submission does not match requested submission"
            )

        if not review.approved:
            raise RobinhoodOrderReviewRejectedError(
                "Robinhood exit order review was not approved"
            )

        require_fresh_quote_timestamp(
            observed_at=quote.observed_at,
            evaluated_at=self._clock(),
            max_quote_age=self._max_quote_age,
        )


        receipt = self._client.submit_exit_order(
            submission
        )

        return ExecutionResult(
            position_id=intent.position_id,
            status=ExecutionStatus.SUBMITTED,
            submitted_at=receipt.submitted_at,
            broker_order_id=receipt.broker_order_id,
            message="Robinhood exit order submitted",
        )