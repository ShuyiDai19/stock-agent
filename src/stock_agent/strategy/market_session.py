from dataclasses import dataclass
from datetime import (
    date,
    datetime,
)
from enum import StrEnum
from zoneinfo import ZoneInfo

import exchange_calendars as xcals


_NEW_YORK = ZoneInfo(
    "America/New_York"
)


class RegularMarketSessionStatus(
    StrEnum
):
    OPEN = "open"
    BEFORE_OPEN = "before_open"
    AFTER_CLOSE = "after_close"
    NO_SESSION = "no_session"


@dataclass(
    frozen=True,
    slots=True,
)
class RegularMarketSession:
    session_date: date

    status: (
        RegularMarketSessionStatus
    )

    opens_at: datetime | None
    closes_at: datetime | None

    def __post_init__(
        self,
    ) -> None:
        if (
            self.status
            is RegularMarketSessionStatus
            .NO_SESSION
        ):
            if (
                self.opens_at is not None
                or self.closes_at
                is not None
            ):
                raise ValueError(
                    "NO_SESSION cannot have "
                    "open or close timestamps"
                )

            return

        if (
            self.opens_at is None
            or self.closes_at is None
        ):
            raise ValueError(
                "market session requires "
                "open and close timestamps"
            )

        if (
            self.opens_at.tzinfo is None
            or self.opens_at.utcoffset()
            is None
            or self.closes_at.tzinfo
            is None
            or self.closes_at.utcoffset()
            is None
        ):
            raise ValueError(
                "session timestamps must "
                "be timezone-aware"
            )

        if (
            self.opens_at
            >= self.closes_at
        ):
            raise ValueError(
                "market open must be "
                "before market close"
            )

    @property
    def is_open(
        self,
    ) -> bool:
        return (
            self.status
            is RegularMarketSessionStatus
            .OPEN
        )


class XnysRegularMarketSessionResolver:
    def __init__(
        self,
    ) -> None:
        self._calendar = (
            xcals.get_calendar(
                "XNYS"
            )
        )

    def resolve(
        self,
        evaluated_at: datetime,
    ) -> RegularMarketSession:
        if (
            evaluated_at.tzinfo is None
            or evaluated_at.utcoffset()
            is None
        ):
            raise ValueError(
                "evaluated_at must be "
                "timezone-aware"
            )

        local_time = (
            evaluated_at.astimezone(
                _NEW_YORK
            )
        )

        session_date = (
            local_time.date()
        )

        session_key = (
            session_date.isoformat()
        )

        if not self._calendar.is_session(
            session_key
        ):
            return RegularMarketSession(
                session_date=(
                    session_date
                ),
                status=(
                    RegularMarketSessionStatus
                    .NO_SESSION
                ),
                opens_at=None,
                closes_at=None,
            )

        opens_at = (
            self._calendar
            .session_open(
                session_key
            )
            .to_pydatetime()
        )

        closes_at = (
            self._calendar
            .session_close(
                session_key
            )
            .to_pydatetime()
        )

        if evaluated_at < opens_at:
            status = (
                RegularMarketSessionStatus
                .BEFORE_OPEN
            )

        elif evaluated_at >= closes_at:
            status = (
                RegularMarketSessionStatus
                .AFTER_CLOSE
            )

        else:
            status = (
                RegularMarketSessionStatus
                .OPEN
            )

        return RegularMarketSession(
            session_date=session_date,
            status=status,
            opens_at=opens_at,
            closes_at=closes_at,
        )