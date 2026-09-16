from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ..categories import CATEGORIES, PAYMENT_MODES
from ..db import get_db
from ..schemas import SuggestIn
from ..security import current_user
from ..services import classifier

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("")
async def list_categories():
    return {"categories": CATEGORIES, "payment_modes": PAYMENT_MODES}


@router.post("/suggest")
async def suggest(body: SuggestIn, user: dict = Depends(current_user)):
    return await classifier.suggest(get_db(), user["_id"], body.merchant, body.items)


@router.get("/overrides")
async def overrides(user: dict = Depends(current_user)):
    rows = await get_db().merchant_overrides.find({"user_id": user["_id"]}).sort("updated_at", -1).to_list(200)
    return [{"merchant": r["merchant"], "category": r["category"]} for r in rows]


@router.post("/retrain")
async def retrain(user: dict = Depends(current_user)):
    """Refit the shared model with everyone's corrections (demo-scale; in production this is a job)."""
    rows = await get_db().category_feedback.find({}, {"text": 1, "category": 1}).to_list(50_000)
    return await run_in_threadpool(classifier.retrain_with_feedback, rows)
