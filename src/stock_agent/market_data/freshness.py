from datetime import datetime, timedelta


DEFAULT_MAX_QUOTE_AGE = timedelta(
    seconds=30
)


class QuoteFreshnessError(
    ValueError
):
    pass


def require_fresh_quote_timestamp(
    *,
    observed_at: datetime,
    evaluated_at: datetime,
    max_quote_age: timedelta = (
        DEFAULT_MAX_QUOTE_AGE
    ),
) -> None:
    if (
        observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise ValueError(
            "observed_at must be timezone-aware"
        )

    if (
        evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        raise ValueError(
            "evaluated_at must be timezone-aware"
        )

    if max_quote_age <= timedelta(0):
        raise ValueError(
            "max_quote_age must be positive"
        )

    quote_age = (
        evaluated_at
        - observed_at
    )

    if quote_age < timedelta(0):
        raise QuoteFreshnessError(
            "quote cannot be from the future"
        )

    if quote_age > max_quote_age:
        raise QuoteFreshnessError(
            "quote is stale"
        )