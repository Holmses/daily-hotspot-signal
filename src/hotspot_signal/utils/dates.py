from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo


def now_in_timezone(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def report_date(value: str | None, timezone: str) -> date:
    if value:
        return date.fromisoformat(value)
    return now_in_timezone(timezone).date()


def parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000.0
        return datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC"))

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_datetime(int(text))

    for parser in (datetime.fromisoformat, parsedate_to_datetime):
        try:
            parsed = parser(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return parsed
    return None


def normalize_datetime(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo(timezone))
    return value.astimezone(ZoneInfo(timezone))
