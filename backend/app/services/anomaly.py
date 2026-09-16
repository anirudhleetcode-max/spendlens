"""Robust per-category outlier detection (pipeline: insights).

For each category we take the user's own last 180 days (a Mongo aggregation groups the amounts) and
compute the median and the MAD (median absolute deviation). The modified z-score is

    z = 0.6745 * (x - median) / MAD          (Iglewicz & Hoaglin, 1993)

0.6745 makes MAD comparable to a standard deviation for normal data, so z = 3.5 means roughly
"3.5 sigma". An expense is flagged when BOTH
    z > Z_THRESHOLD (3.5)          - far from this user's typical spend in the category, and
    x >= MIN_RATIO (2) x median     - big in absolute terms (stops a category with near-zero spread
                                      from flagging Rs 320 against a typical Rs 300).
Needs MIN_HISTORY (6) expenses in the category. If MAD is 0 (all amounts equal) it falls back to
10 % of the median.

Why median/MAD and not mean/std: a single Rs 9,000 purchase inflates the std and hides itself; the
median and MAD barely move. Why not IsolationForest: a new user has a handful of rows per category,
and a per-category rule gives a sentence the user can check ("9.5x your usual Food & Dining spend").
Only large, unusual *amounts* are detected - not duplicates, not frequency changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np


@dataclass(frozen=True)
class AnomalyRule:
    z_threshold: float = 3.5
    min_ratio: float = 2.0
    min_history: int = 6
    window_days: int = 180


RULE = AnomalyRule()
# kept for backwards compatibility with earlier imports
MIN_HISTORY, Z_THRESHOLD, MIN_RATIO = RULE.min_history, RULE.z_threshold, RULE.min_ratio


def robust_stats(amounts: list[float], rule: AnomalyRule = RULE) -> tuple[float, float] | None:
    if len(amounts) < rule.min_history:
        return None
    a = np.asarray(amounts, dtype=float)
    med = float(np.median(a))
    mad = float(np.median(np.abs(a - med)))
    if mad == 0:
        mad = max(1.0, 0.1 * med)
    return med, mad


def score(amount: float, stats: tuple[float, float]) -> tuple[float, float]:
    med, mad = stats
    return 0.6745 * (amount - med) / mad, amount / med if med > 0 else float("inf")


def is_anomaly(amount: float, stats: tuple[float, float] | None, rule: AnomalyRule = RULE) -> tuple[bool, float, float]:
    if not stats:
        return False, 0.0, 0.0
    z, ratio = score(amount, stats)
    return (z > rule.z_threshold and ratio >= rule.min_ratio), z, ratio


def explain(category: str, amount: float, stats: tuple[float, float], rule: AnomalyRule = RULE) -> dict:
    """Plain-language reason + the numbers behind it (shown in the UI tooltip)."""
    z, ratio = score(amount, stats)
    med = stats[0]
    return {
        "z": round(z, 1), "ratio": round(ratio, 1), "median": round(med, 2),
        "reason": f"{ratio:.1f}× your usual {category} spend",
        "detail": (f"Typical {category} expense is ₹{med:,.0f}. This one is {ratio:.1f}× that "
                   f"(robust z = {z:.1f}; flagged above z {rule.z_threshold} and {rule.min_ratio:g}×)."),
        "rule": {"z_threshold": rule.z_threshold, "min_ratio": rule.min_ratio, "min_history": rule.min_history},
    }


async def category_stats(db, user_id, days: int = RULE.window_days) -> dict[str, tuple[float, float]]:
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
    """Adds an 'anomaly' dict to expenses that are unusual for their category (None otherwise)."""
    for e in expenses:
        st = stats.get(e["category"])
        flag, _, _ = is_anomaly(e["amount"], st)
        e["anomaly"] = explain(e["category"], e["amount"], st) if flag else None
    return expenses
