def parse_live_execution_enabled(
    value: str | None,
) -> bool:
    if value is None:
        return False

    normalized = value.strip().lower()

    if normalized == "true":
        return True

    if normalized == "false":
        return False

    raise ValueError(
        "ENABLE_LIVE_EXECUTION must be 'true' or 'false'"
    )