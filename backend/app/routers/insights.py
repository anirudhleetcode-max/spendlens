from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from ..db import get_db
from ..security import current_user
from ..services import anomaly
from ..utils import current_month, days_in_month, month_bounds, shift_month
from .budgets import budget_status
from .expenses import public

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/overview")
async def overview(month: str = Query(default_factory=current_month, pattern=r"^\d{4}-\d{2}$"),
                   user: dict = Depends(current_user)):
    db = get_db()
    uid = user["_id"]
    start, end = month_bounds(month)
    prev = shift_month(month, -1)
    pstart, pend = month_bounds(prev)

    facet = await db.expenses.aggregate([
        {"$match": {"user_id": uid, "date": {"$gte": pstart, "$lt": end}}},
        {"$facet": {
            "prev": [{"$match": {"date": {"$lt": pend}}},
                     {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}],
            "totals": [{"$match": {"date": {"$gte": start}}},
                       {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1},
                                   "tax": {"$sum": "$tax"}}}],
            "by_category": [{"$match": {"date": {"$gte": start}}},
                            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
                            {"$sort": {"total": -1}}],
            "prev_by_category": [{"$match": {"date": {"$lt": pend}}},
                                 {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}],
            "daily": [{"$match": {"date": {"$gte": start}}},
                      {"$group": {"_id": {"$dayOfMonth": "$date"}, "total": {"$sum": "$amount"}}}],
            "prev_daily": [{"$match": {"date": {"$lt": pend}}},
                           {"$group": {"_id": {"$dayOfMonth": "$date"}, "total": {"$sum": "$amount"}}}],
            "merchants": [{"$match": {"date": {"$gte": start}}},
                          {"$group": {"_id": "$merchant_key", "merchant": {"$first": "$merchant"},
                                      "category": {"$first": "$category"},
                                      "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
                          {"$sort": {"total": -1}}, {"$limit": 6}],
            "month_rows": [{"$match": {"date": {"$gte": start}}}, {"$sort": {"amount": -1}}, {"$limit": 200}],
        }},
    ]).to_list(1)
    f = facet[0]
    total = round(f["totals"][0]["total"], 2) if f["totals"] else 0.0
    count = f["totals"][0]["count"] if f["totals"] else 0
    prev_total = round(f["prev"][0]["total"], 2) if f["prev"] else 0.0

    # cumulative daily series for this month and last month, so the line shows pace, not noise
    def cumulative(rows, n):
        per_day = {r["_id"]: r["total"] for r in rows}
        out, run = [], 0.0
        for d in range(1, n + 1):
            run += per_day.get(d, 0.0)
            out.append({"day": d, "amount": round(per_day.get(d, 0.0), 2), "cumulative": round(run, 2)})
        return out

    daily = cumulative(f["daily"], days_in_month(month))
    prev_daily = cumulative(f["prev_daily"], days_in_month(prev))
    # a month in progress is compared with the same days of last month, not the whole of it
    in_progress = month == current_month()
    upto = min(datetime.now(timezone.utc).day, len(prev_daily)) if in_progress else len(prev_daily)
    prev_to_date = prev_daily[upto - 1]["cumulative"] if prev_daily else 0.0

    stats = await anomaly.category_stats(db, uid)
    rows = anomaly.annotate(f["month_rows"], stats)
    anomalies = [public(r) for r in rows if r.get("anomaly")][:6]
    prev_cat = {r["_id"]: r["total"] for r in f["prev_by_category"]}

    return {
        "month": month,
        "total": total,
        "count": count,
        "tax": round(f["totals"][0]["tax"], 2) if f["totals"] else 0.0,
        "previous_month": prev,
        "previous_total": prev_total,
        "previous_to_date": prev_to_date,
        "compared_days": upto if in_progress else None,
        "change_pct": round(100 * (total - prev_to_date) / prev_to_date, 1) if prev_to_date else None,
        "by_category": [{"category": r["_id"], "total": round(r["total"], 2), "count": r["count"],
                         "previous": round(prev_cat.get(r["_id"], 0.0), 2)} for r in f["by_category"]],
        "daily": daily,
        "previous_daily": prev_daily,
        "top_merchants": [{"merchant": r["merchant"], "category": r["category"], "total": round(r["total"], 2),
                           "count": r["count"]} for r in f["merchants"]],
        "anomalies": anomalies,
        "budgets": await budget_status(db, uid, month),
    }
