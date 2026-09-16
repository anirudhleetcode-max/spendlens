from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from ..categories import CATEGORIES
from ..db import get_db
from ..schemas import BudgetIn
from ..security import current_user
from ..utils import current_month, days_in_month, month_bounds

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def month_progress(month: str) -> tuple[int, int]:
    """(days elapsed, days in month). Past months are complete, future months have 0 elapsed."""
    dim = days_in_month(month)
    cur = current_month()
    if month < cur:
        return dim, dim
    if month > cur:
        return 0, dim
    return datetime.now(timezone.utc).day, dim


def project(spent: float, elapsed: int, dim: int) -> float:
    """Linear pace: if you keep spending at this month's daily average, where do you end up?"""
    if elapsed <= 0:
        return 0.0
    return spent / elapsed * dim


async def budget_status(db, user_id, month: str) -> list[dict]:
    budgets = await db.budgets.find({"user_id": user_id}).to_list(len(CATEGORIES))
    if not budgets:
        return []
    start, end = month_bounds(month)
    spent_rows = await db.expenses.aggregate([
        {"$match": {"user_id": user_id, "date": {"$gte": start, "$lt": end},
                    "category": {"$in": [b["category"] for b in budgets]}}},
        {"$group": {"_id": "$category", "spent": {"$sum": "$amount"}}},
    ]).to_list(None)
    spent = {r["_id"]: r["spent"] for r in spent_rows}
    elapsed, dim = month_progress(month)
    out = []
    for b in sorted(budgets, key=lambda b: CATEGORIES.index(b["category"])):
        s = round(spent.get(b["category"], 0.0), 2)
        proj = round(project(s, elapsed, dim), 2)
        status = "over" if s > b["amount"] else "at_risk" if proj > b["amount"] else "ok"
        out.append({"category": b["category"], "budget": b["amount"], "spent": s, "projected": proj,
                    "pct": round(100 * s / b["amount"], 1), "status": status,
                    "remaining": round(b["amount"] - s, 2)})
    return out


@router.get("")
async def list_budgets(month: str = Query(default_factory=current_month, pattern=r"^\d{4}-\d{2}$"),
                       user: dict = Depends(current_user)):
    elapsed, dim = month_progress(month)
    return {"month": month, "days_elapsed": elapsed, "days_in_month": dim,
            "budgets": await budget_status(get_db(), user["_id"], month)}


@router.put("")
async def upsert(body: BudgetIn, user: dict = Depends(current_user)):
    await get_db().budgets.update_one(
        {"user_id": user["_id"], "category": body.category},
        {"$set": {"amount": round(body.amount, 2), "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"category": body.category, "amount": round(body.amount, 2)}


@router.delete("/{category}", status_code=204)
async def remove(category: str, user: dict = Depends(current_user)):
    res = await get_db().budgets.delete_one({"user_id": user["_id"], "category": category})
    if not res.deleted_count:
        raise HTTPException(404, "No budget for that category")
