import re
from calendar import monthrange
from datetime import date, datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(404, "Not found")


def merchant_key(name: str) -> str:
    """Normalised merchant used for overrides and grouping: 'D-Mart  Ltd.' -> 'd mart ltd'."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def month_bounds(month: str) -> tuple[datetime, datetime]:
    """'2026-09' -> [2026-09-01, 2026-10-01) as UTC datetimes."""
    try:
        y, m = (int(p) for p in month.split("-"))
        start = datetime(y, m, 1, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        raise HTTPException(422, "month must look like YYYY-MM")
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc)
    return start, end


def shift_month(month: str, delta: int) -> str:
    y, m = (int(p) for p in month.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def days_in_month(month: str) -> int:
    y, m = (int(p) for p in month.split("-"))
    return monthrange(y, m)[1]


def to_utc_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
