"""Basic-plan daily bars are available after the trading day's midnight ET."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars


EASTERN = ZoneInfo("America/New_York")


def latest_published_session(now: datetime):
    if now.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    yesterday = now.astimezone(EASTERN).date() - timedelta(days=1)
    calendar = exchange_calendars.get_calendar("XNYS")
    return calendar.date_to_session(yesterday, direction="previous").date()


def is_session(day):
    return exchange_calendars.get_calendar("XNYS").is_session(day)


def sessions(start, end):
    return [stamp.date() for stamp in exchange_calendars.get_calendar("XNYS").sessions_in_range(start, end)]
