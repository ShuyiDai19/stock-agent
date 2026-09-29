from typing import Any
from urllib.parse import (
    parse_qs,
    urlsplit,
)


def extract_robinhood_order_next_cursor(
    raw_result: Any,
) -> str | None:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood order result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood order result "
            "must contain data"
        )

    markers = [
        envelope["next"]
        for envelope in (
            raw_result,
            data,
        )
        if "next" in envelope
    ]

    if not markers:
        return None

    if any(
        marker != markers[0]
        for marker in markers[1:]
    ):
        raise ValueError(
            "Robinhood order pagination "
            "metadata conflicts"
        )

    next_value = markers[0]

    if next_value is None:
        return None

    if (
        not isinstance(
            next_value,
            str,
        )
        or not next_value.strip()
    ):
        raise ValueError(
            "Robinhood order next must "
            "be a nonempty URL"
        )

    parsed = urlsplit(
        next_value
    )

    if (
        parsed.scheme != "https"
        or not parsed.netloc
    ):
        raise ValueError(
            "Robinhood order next must "
            "be an HTTPS URL"
        )

    cursors = parse_qs(
        parsed.query,
        keep_blank_values=True,
    ).get(
        "cursor",
        [],
    )

    if (
        len(cursors) != 1
        or not cursors[0]
    ):
        raise ValueError(
            "Robinhood order next must "
            "contain one cursor"
        )

    return cursors[0]