import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ..categories import CATEGORIES, MODEL_CATEGORIES, PAYMENT_MODES, UNCATEGORISED
from ..config import get_settings
from ..db import get_db
from ..pipeline.confidence import REVIEW_THRESHOLD
from ..pipeline.ocr import ocr_status
from ..pipeline.preprocess import PREPROCESS_VERSION
from ..pipeline.receipt import PARSER_VERSION
from ..schemas import SuggestIn
from ..security import current_user
from ..services import anomaly, classifier

router = APIRouter(prefix="/api/categories", tags=["categories"])
model_router = APIRouter(prefix="/api", tags=["model"])
RESULTS = Path(__file__).resolve().parents[3] / "experiments" / "results"


@router.get("")
async def list_categories():
    return {"categories": CATEGORIES, "model_categories": MODEL_CATEGORIES, "uncategorised": UNCATEGORISED,
            "payment_modes": PAYMENT_MODES}


@router.post("/suggest")
async def suggest(body: SuggestIn, user: dict = Depends(current_user)):
    return await classifier.suggest(get_db(), user["_id"], body.merchant, body.items)


@router.get("/overrides")
async def overrides(user: dict = Depends(current_user)):
    rows = await get_db().merchant_overrides.find({"user_id": user["_id"]}).sort("updated_at", -1).to_list(200)
    return [{"merchant": r["merchant"], "category": r["category"]} for r in rows]


def is_admin(user: dict) -> bool:
    admins = {e.strip().lower() for e in get_settings().admin_emails.split(",") if e.strip()}
    return user.get("email", "").lower() in admins


@router.post("/retrain")
async def retrain(user: dict = Depends(current_user)):
    """Refit the shared model with everyone's corrections. Admin only: a retrain changes suggestions
    for all users, so it must not be triggerable by any account (data poisoning)."""
    if not is_admin(user):
        raise HTTPException(403, "Only an admin can retrain the shared model (set ADMIN_EMAILS)")
    rows = await get_db().category_feedback.find({}, {"text": 1, "category": 1}).to_list(50_000)
    return await run_in_threadpool(classifier.retrain_with_feedback, rows)


def _latest(prefix: str) -> dict | None:
    runs = sorted(RESULTS.glob(f"{prefix}-*/metrics.json")) if RESULTS.exists() else []
    if not runs:
        return None
    try:
        return json.loads(runs[-1].read_text())
    except (OSError, ValueError):
        return None


def _receipt_summary(prefix: str, variant: str = "preprocess_dual_psm6") -> dict | None:
    m = _latest(prefix)
    if not m:
        return None
    v = m["variants"].get(variant) or next(iter(m["variants"].values()))
    ds = m["dataset"]
    return {"run_id": m.get("run_id"), "dataset": ds.get("title") or ds.get("name"), "synthetic": ds.get("synthetic"),
            "n": v.get("n_receipts"),
            "merchant_exact": (v.get("merchant") or {}).get("exact"),
            "date_exact": (v.get("date") or {}).get("exact"),
            "total_exact": (v.get("total") or {}).get("exact"),
            "cer": (v.get("ocr") or {}).get("cer_mean")}


@model_router.get("/model")
async def model_info():
    """Model card for the category model + metadata of the receipt pipeline + latest evaluation runs."""
    m = classifier.get_model()
    return {
        "category_model": m.info(),
        "receipt_pipeline": {
            "ocr": ocr_status(), "preprocess_version": PREPROCESS_VERSION, "parser_version": PARSER_VERSION,
            "review_threshold": REVIEW_THRESHOLD, "method": "OpenCV preprocessing + Tesseract 5 + rule-based extraction",
        },
        "anomaly_rule": anomaly.RULE.__dict__,
        "evaluations": {
            "receipts_real_sroie": _receipt_summary("sroie_main"),
            "receipts_real_cord": _receipt_summary("cord_main"),
            "receipts_synthetic_test": _receipt_summary("synthetic_test"),
        },
        "notes": [
            "The category model is trained and evaluated on SYNTHETIC data only.",
            "Receipt extraction is evaluated on real Malaysian (SROIE) and Indonesian (CORD) receipts and on "
            "synthetic Indian receipts; no labelled Indian receipt set was available.",
        ],
    }
