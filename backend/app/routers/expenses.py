import csv
import io
import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..categories import CATEGORIES
from ..db import get_bucket, get_db
from ..schemas import ExpenseIn, ExpensePatch
from ..security import current_user
from ..services import anomaly, classifier
from ..utils import current_month, merchant_key, month_bounds, oid, to_utc_midnight

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


def public(e: dict) -> dict:
    return {
        "id": str(e["_id"]), "merchant": e["merchant"], "amount": e["amount"], "tax": e.get("tax", 0),
        "date": e["date"].date().isoformat(), "category": e["category"],
        "payment_mode": e.get("payment_mode", "Unknown"), "items": e.get("items", []),
        "notes": e.get("notes", ""), "source": e.get("source", "manual"),
        "receipt_id": str(e["receipt_id"]) if e.get("receipt_id") else None,
        "suggested_category": e.get("suggested_category"),
        "created_at": e["created_at"].isoformat() if e.get("created_at") else None,
        "anomaly": e.get("anomaly"),
        "demo": bool(e.get("demo")),
    }


def _filter(user_id, month: str | None, category: str | None, q: str | None) -> dict:
    f: dict = {"user_id": user_id}
    if month:
        start, end = month_bounds(month)
        f["date"] = {"$gte": start, "$lt": end}
    if category:
        if category not in CATEGORIES:
            raise HTTPException(422, "Unknown category")
        f["category"] = category
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()[:60]), "$options": "i"}
        f["$or"] = [{"merchant": rx}, {"items.name": rx}, {"notes": rx}]
    return f


@router.get("")
async def list_expenses(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    category: str | None = None,
    q: str | None = Query(None, max_length=60),
    page: int = Query(1, ge=1, le=10_000),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
):
    db = get_db()
    f = _filter(user["_id"], month, category, q)
    # one round trip: page of rows + count + sum
    res = await db.expenses.aggregate([
        {"$match": f},
        {"$facet": {
            "rows": [{"$sort": {"date": -1, "_id": -1}}, {"$skip": (page - 1) * limit}, {"$limit": limit}],
            "meta": [{"$group": {"_id": None, "count": {"$sum": 1}, "sum": {"$sum": "$amount"}}}],
        }},
    ]).to_list(1)
    rows = res[0]["rows"]
    meta = res[0]["meta"][0] if res[0]["meta"] else {"count": 0, "sum": 0}
    stats = await anomaly.category_stats(db, user["_id"])
    anomaly.annotate(rows, stats)
    return {"items": [public(r) for r in rows], "total": meta["count"], "sum": round(meta["sum"], 2),
            "page": page, "pages": max(1, math.ceil(meta["count"] / limit)), "limit": limit}


async def _check_receipt(db, user_id, receipt_id: str | None):
    if not receipt_id:
        return None
    _id = oid(receipt_id)
    if not await db["receipts.files"].find_one({"_id": _id, "metadata.user_id": user_id}, {"_id": 1}):
        raise HTTPException(422, "Receipt not found")
    return _id


@router.post("", status_code=201)
async def create(body: ExpenseIn, user: dict = Depends(current_user)):
    db = get_db()
    uid = user["_id"]
    item_names = [i.name for i in body.items]
    suggested = body.suggested_category
    category = body.category
    if category is None:
        s = await classifier.suggest(db, uid, body.merchant, item_names)
        suggested = s["category"] if s["status"] != "unavailable" else None
        category = classifier.resolved_category(s)
    elif suggested and suggested != category:
        await classifier.record_correction(db, uid, body.merchant, item_names, category, suggested)
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": uid, "merchant": body.merchant, "merchant_key": merchant_key(body.merchant),
        "amount": round(body.amount, 2), "tax": round(body.tax, 2), "date": to_utc_midnight(body.date),
        "category": category, "suggested_category": suggested, "payment_mode": body.payment_mode,
        "items": [i.model_dump() for i in body.items], "notes": body.notes,
        "receipt_id": await _check_receipt(db, uid, body.receipt_id),
        "source": "scan" if body.receipt_id else "manual", "created_at": now, "updated_at": now,
    }
    res = await db.expenses.insert_one(doc)
    doc["_id"] = res.inserted_id
    if doc["receipt_id"]:
        from .receipts import mark_attached
        await mark_attached(doc["receipt_id"])
    return public(doc)


@router.get("/export")
async def export_csv(month: str = Query(default_factory=current_month, pattern=r"^\d{4}-\d{2}$"),
                     user: dict = Depends(current_user)):
    f = _filter(user["_id"], month, None, None)
    cursor = get_db().expenses.find(f).sort("date", 1)

    async def rows():
        buf = io.StringIO()
        w = csv.writer(buf)
        buf.write("﻿")  # BOM so Excel on Windows opens UTF-8 (₹, names) correctly
        w.writerow(["Date", "Merchant", "Category", "Amount (INR)", "Tax (INR)", "Payment mode", "Items", "Notes", "Source"])
        async for e in cursor:
            w.writerow([e["date"].date().isoformat(), e["merchant"], e["category"], f"{e['amount']:.2f}",
                        f"{e.get('tax', 0):.2f}", e.get("payment_mode", ""),
                        "; ".join(f"{i['name']} x{i['qty']:g}" for i in e.get("items", [])),
                        e.get("notes", ""), e.get("source", "")])
            yield buf.getvalue()
            buf.seek(0); buf.truncate()
        yield buf.getvalue()

    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="spendlens-{month}.csv"'})


@router.get("/{expense_id}")
async def get_one(expense_id: str, user: dict = Depends(current_user)):
    e = await get_db().expenses.find_one({"_id": oid(expense_id), "user_id": user["_id"]})
    if not e:
        raise HTTPException(404, "Expense not found")
    return public(e)


@router.patch("/{expense_id}")
async def update(expense_id: str, body: ExpensePatch, user: dict = Depends(current_user)):
    db = get_db()
    e = await db.expenses.find_one({"_id": oid(expense_id), "user_id": user["_id"]})
    if not e:
        raise HTTPException(404, "Expense not found")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "date" in changes:
        changes["date"] = to_utc_midnight(changes["date"])
    if "merchant" in changes:
        changes["merchant"] = changes["merchant"].strip()
        changes["merchant_key"] = merchant_key(changes["merchant"])
    for k in ("amount", "tax"):
        if k in changes:
            changes[k] = round(changes[k], 2)
    if "category" in changes and changes["category"] != e["category"]:
        items = [i["name"] for i in changes.get("items", e.get("items", []))]
        await classifier.record_correction(db, user["_id"], changes.get("merchant", e["merchant"]), items,
                                           changes["category"], e["category"])
    changes["updated_at"] = datetime.now(timezone.utc)
    updated = await db.expenses.find_one_and_update({"_id": e["_id"], "user_id": user["_id"]}, {"$set": changes},
                                                    return_document=True)
    return public(updated)


@router.delete("/{expense_id}", status_code=204)
async def delete(expense_id: str, user: dict = Depends(current_user)):
    db = get_db()
    e = await db.expenses.find_one_and_delete({"_id": oid(expense_id), "user_id": user["_id"]})
    if not e:
        raise HTTPException(404, "Expense not found")
    if e.get("receipt_id"):
        try:
            await get_bucket().delete(e["receipt_id"])
        except Exception:
            pass
