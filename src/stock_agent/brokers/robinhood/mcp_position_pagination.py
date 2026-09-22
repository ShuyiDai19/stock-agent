from typing import Any
from urllib.parse import (
    parse_qs,
    urlparse,
)


class RobinhoodPositionPaginationError(
    ValueError
):
    pass


_MISSING = object()


def extract_robinhood_position_next_cursor(
    payload: Any,
) -> str | None:
    if not isinstance(
        payload,
        dict,
    ):
        raise RobinhoodPositionPaginationError(
            "position result must be a mapping"
        )

    top_level_next = payload.get(
        "next",
        _MISSING,
    )

    data = payload.get("data")

    if isinstance(data, dict):
        nested_next = data.get(
            "next",
            _MISSING,
        )
    else:
        nested_next = _MISSING

    if (
        top_level_next is _MISSING
        and nested_next is _MISSING
    ):
        return None

    if (
        top_level_next is not _MISSING
        and nested_next is not _MISSING
        and top_level_next != nested_next
    ):
        raise RobinhoodPositionPaginationError(
            "conflicting pagination metadata"
        )

    next_value = (
        top_level_next
        if top_level_next is not _MISSING
        else nested_next
    )

    if next_value is None:
        return None

    if not isinstance(
        next_value,
        str,
    ):
        raise RobinhoodPositionPaginationError(
            "next must be a string or null"
        )

    next_url = next_value.strip()

    if not next_url:
        raise RobinhoodPositionPaginationError(
            "next must not be empty"
        )

    parsed = urlparse(
        next_url
    )

    if parsed.scheme != "https":
        raise RobinhoodPositionPaginationError(
            "next must use https"
        )

    query = parse_qs(
        parsed.query,
        keep_blank_values=True,
    )

    cursors = query.get(
        "cursor"
    )

    if (
        cursors is None
        or len(cursors) != 1
        or not cursors[0].strip()
    ):
        raise RobinhoodPositionPaginationError(
            "next must contain exactly "
            "one non-empty cursor"
        )

    return cursors[0]