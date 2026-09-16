"""Robust per-category outlier detection.

For each category we take the user's recent history (Mongo aggregation groups the amounts) and compute
the median and MAD (median absolute deviation). The modified z-score is
    z = 0.6745 * (x - median) / MAD          (Iglewicz & Hoaglin)
An expense is flagged when z > 3.5 AND it is at least 2x the category median - the second rule keeps
tiny categories with near-zero MAD from flagging every small variation. Median/MAD are used instead of
mean/std because a single big purchase would inflate the std and hide itself.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

MIN_HISTORY = 6
Z_THRESHOLD = 3.5
MIN_RATIO = 2.0


def robust_stats(amounts: list[float]) -> tuple[float, float] | None:
    if len(amounts) < MIN_HISTORY:
        return None
    a = np.asarray(amounts, dtype=float)
    med = float(np.median(a))
    mad = float(np.median(np.abs(a - med)))
    if mad == 0:
        mad = max(1.0, 0.1 * med)  # all equal amounts: fall back to 10 % of the median
    return med, mad


def score(amount: float, stats: tuple[float, float]) -> tuple[float, float]:
    med, mad = stats
    return 0.6745 * (amount - med) / mad, amount / med if med > 0 else float("inf")


def is_anomaly(amount: float, stats: tuple[float, float] | None) -> tuple[bool, float, float]:
    if not stats:
        return False, 0.0, 0.0
    z, ratio = score(amount, stats)
    return (z > Z_THRESHOLD and ratio >= MIN_RATIO), z, ratio


async def category_stats(db, user_id, days: int = 180) -> dict[str, tuple[float, float]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.expenses.aggregate([
        {"$match": {"user_id": user_id, "date": {"$gte": since}}},
        {"$group": {"_id": "$category", "amounts": {"$push": "$amount"}}},
    ])
    out = {}
    async for r in rows:
        st = robust_stats(r["amounts"])
        if st:
            out[r["_id"]] = st
    return out


def annotate(expenses: list[dict], stats: dict) -> list[dict]:
    """Adds an 'anomaly' dict to expenses that are unusual for their category."""
    for e in expenses:
        flag, z, ratio = is_anomaly(e["amount"], stats.get(e["category"]))
        e["anomaly"] = ({"z": round(z, 1), "ratio": round(ratio, 1), "median": round(stats[e["category"]][0], 2),
                         "reason": f"{ratio:.1f}× your usual {e['category']} spend"} if flag else None)
    return expenses
