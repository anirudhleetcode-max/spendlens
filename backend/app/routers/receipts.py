"""Receipt scanning. A scan stores the (shrunk) photo in GridFS with metadata.status = "pending";
saving an expense with that receipt_id marks it "attached". Pending scans are discarded by the user
(DELETE) or by the periodic cleanup after ORPHAN_RECEIPT_HOURS."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ..categories import UNCATEGORISED
from ..config import get_settings
from ..db import get_bucket, get_db
from ..pipeline.ocr import ocr_status, run_ocr
from ..pipeline.preprocess import decode
from ..pipeline.receipt import parse_lines
from ..security import current_user
from ..services import classifier
from ..services.images import shrink_jpeg
from ..services.uploads import read_image_upload
from ..utils import oid

router = APIRouter(prefix="/api/receipts", tags=["receipts"])
log = logging.getLogger(__name__)


def _empty_fields() -> dict:
    return {k: {"value": v, "confidence": 0.0, "source": "none"} for k, v in
            {"merchant": "", "date": None, "total": None, "tax": 0.0, "payment_mode": "Unknown"}.items()}


def _process(data: bytes, ocr_on: bool) -> tuple[bytes, dict | None]:
    decode(data)  # validates the image (format, pixel limit) before any work, raises ValueError
    stored = shrink_jpeg(data)
    if not ocr_on:
        return stored, None
    ocr = run_ocr(data, want_preview=True)
    parsed = parse_lines(ocr["lines"])
    parsed["ocr"] = {"mean_conf": ocr["mean_conf"], "skew": ocr["skew"], "cropped": ocr["cropped"],
                     "variant": ocr["variant"], "ms": ocr["ms"],
                     "lines": [{"text": l.text, "conf": l.conf} for l in ocr["lines"]],
                     "preview": ocr.get("preview")}
    return stored, parsed


@router.post("/scan", status_code=201)
async def scan(file: UploadFile = File(...), user: dict = Depends(current_user)):
    s = get_settings()
    data, kind = await read_image_upload(file, s.max_upload_mb * 1024 * 1024)
    status = ocr_status()
    try:
        stored, parsed = await run_in_threadpool(_process, data, status["available"])
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:  # tesseract timeout / crash
        log.warning("OCR failed: %s", e)
        raise HTTPException(503, "Reading the receipt took too long. Try a smaller or sharper photo.")

    now = datetime.now(timezone.utc)
    receipt_id = await get_bucket().upload_from_stream(
        "receipt.jpg", stored,  # never the client's file name
        metadata={"user_id": user["_id"], "content_type": "image/jpeg", "original_type": kind,
                  "original_bytes": len(data), "uploaded_at": now, "status": "pending"},
    )
    fields = parsed["fields"] if parsed else _empty_fields()
    items = parsed["items"] if parsed else []
    suggestion = await classifier.suggest(get_db(), user["_id"], fields["merchant"]["value"] or "",
                                          [i["name"] for i in items])
    if parsed is None:
        suggestion.update(confidence=0.0, status="unavailable", abstained=True, category=UNCATEGORISED,
                          detail="OCR is off, so there is no text to classify yet.")
    log.info("scan stored=%dB ocr=%s fields=%s", len(stored), status["available"],
             {k: v["confidence"] for k, v in fields.items()})
    return {
        "receipt_id": str(receipt_id),
        "ocr_available": status["available"],
        "fields": fields,
        "items": items,
        "category": suggestion,
        "checks": parsed["checks"] if parsed else [],
        "review_threshold": parsed["review_threshold"] if parsed else 0.6,
        "parser_version": parsed["parser_version"] if parsed else None,
        "ocr": parsed["ocr"] if parsed else None,
        "stored_bytes": len(stored),
        "expires_hours": s.orphan_receipt_hours,
    }


async def _owned(receipt_id: str, user) -> dict:
    doc = await get_db()["receipts.files"].find_one({"_id": oid(receipt_id), "metadata.user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Receipt not found")
    return doc


@router.get("/{receipt_id}/image")
async def image(receipt_id: str, user: dict = Depends(current_user)):
    doc = await _owned(receipt_id, user)
    stream = await get_bucket().open_download_stream(ObjectId(doc["_id"]))
    data = await stream.read()
    return Response(data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.delete("/{receipt_id}", status_code=204)
async def discard(receipt_id: str, user: dict = Depends(current_user)):
    """Throw away a scan that was not saved. Attached receipts are deleted with their expense instead."""
    doc = await _owned(receipt_id, user)
    if (doc.get("metadata") or {}).get("status") != "pending":
        raise HTTPException(409, "This receipt belongs to a saved expense; delete the expense instead")
    await get_bucket().delete(doc["_id"])


async def mark_attached(receipt_oid) -> None:
    await get_db()["receipts.files"].update_one({"_id": receipt_oid}, {"$set": {"metadata.status": "attached"}})


async def cleanup_orphans(hours: int | None = None) -> int:
    """Delete pending scans older than `hours`. Returns how many were removed."""
    hours = get_settings().orphan_receipt_hours if hours is None else hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    bucket = get_bucket()
    removed = 0
    async for doc in get_db()["receipts.files"].find(
            {"metadata.status": "pending", "metadata.uploaded_at": {"$lt": cutoff}}, {"_id": 1}):
        try:
            await bucket.delete(doc["_id"])
            removed += 1
        except Exception:  # already gone
            pass
    if removed:
        log.info("removed %d orphan receipt image(s)", removed)
    return removed
