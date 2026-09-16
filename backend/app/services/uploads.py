"""Upload validation. The Content-Type header and file name are client-controlled, so the decision is
made from the first bytes of the file (magic numbers) and then by Pillow actually parsing it."""
from __future__ import annotations

from fastapi import HTTPException, UploadFile

SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [],  # RIFF....WEBP, checked below
}


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_image_upload(file: UploadFile, max_bytes: int) -> tuple[bytes, str]:
    """Returns (bytes, sniffed mime). Raises 415 / 413 / 422 with a user-facing message.
    Starlette spools large uploads to a temp file; it is closed (and deleted) here in every case."""
    try:
        declared = (file.content_type or "").lower()
        if declared and not declared.startswith("image/") and declared != "application/octet-stream":
            raise HTTPException(415, "Upload a JPG, PNG or WebP photo of the receipt")
        data = await file.read(max_bytes + 1)
    finally:
        await file.close()
    if len(data) > max_bytes:
        raise HTTPException(413, f"Image is larger than {max_bytes // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    kind = sniff(data)
    if kind is None:
        raise HTTPException(415, "That file isn't a JPG, PNG or WebP image")
    return data, kind
