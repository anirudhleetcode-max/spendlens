from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ..config import get_settings
from ..db import get_bucket, get_db
from ..security import current_user
from ..services import classifier
from ..services.images import shrink_jpeg
from ..services.ocr import decode, ocr_image, ocr_status
from ..services.parser import parse_receipt
from ..utils import oid

router = APIRouter(prefix="/api/receipts", tags=["receipts"])
ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/jpg"}


def _empty_fields() -> dict:
    return {k: {"value": v, "confidence": 0.0} for k, v in
            {"merchant": "", "date": None, "total": None, "tax": 0.0, "payment_mode": "Unknown"}.items()}


def _process(data: bytes, ocr_on: bool) -> tuple[bytes, dict | None]:
    decode(data)  # validates the image early, raises ValueError
    stored = shrink_jpeg(data)
    if not ocr_on:
        return stored, None
    ocr = ocr_image(data)
    parsed = parse_receipt(ocr["lines"])
    parsed["ocr"] = {"mean_conf": ocr["mean_conf"], "skew": ocr["skew"], "cropped": ocr["cropped"],
                     "variant": ocr["variant"], "ms": ocr["ms"],
                     "lines": [{"text": l.text, "conf": l.conf} for l in ocr["lines"]]}
    return stored, parsed


@router.post("/scan", status_code=201)
async def scan(file: UploadFile = File(...), user: dict = Depends(current_user)):
    if (file.content_type or "").lower() not in ALLOWED:
        raise HTTPException(415, "Upload a JPG, PNG or WebP photo of the receipt")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Image is larger than {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "The file is empty")

    status = ocr_status()
    try:
        stored, parsed = await run_in_threadpool(_process, data, status["available"])
    except ValueError as e:
        raise HTTPException(422, str(e))

    receipt_id = await get_bucket().upload_from_stream(
        (file.filename or "receipt.jpg")[:100], stored,
        metadata={"user_id": user["_id"], "content_type": "image/jpeg", "original_bytes": len(data),
                  "uploaded_at": datetime.now(timezone.utc)},
    )
    fields = parsed["fields"] if parsed else _empty_fields()
    items = parsed["items"] if parsed else []
    suggestion = await classifier.suggest(get_db(), user["_id"], fields["merchant"]["value"] or "",
                                          [i["name"] for i in items])
    if parsed is None:
        suggestion["confidence"] = 0.0
    return {
        "receipt_id": str(receipt_id),
        "ocr_available": status["available"],
        "fields": fields,
        "items": items,
        "category": suggestion,
        "ocr": parsed["ocr"] if parsed else None,
        "stored_bytes": len(stored),
    }


@router.get("/{receipt_id}/image")
async def image(receipt_id: str, user: dict = Depends(current_user)):
    _id = oid(receipt_id)
    doc = await get_db()["receipts.files"].find_one({"_id": _id, "metadata.user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Receipt not found")
    stream = await get_bucket().open_download_stream(ObjectId(_id))
    data = await stream.read()
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
