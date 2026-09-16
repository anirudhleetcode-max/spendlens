"""Shrink receipt photos before they go into GridFS (<= 1 MB, <= 1600 px long side)."""
import io

from PIL import Image, ImageOps

MAX_BYTES = 1_000_000


def shrink_jpeg(data: bytes, long_side: int = 1600) -> bytes:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((long_side, long_side), Image.LANCZOS)
    for quality in (85, 75, 65, 55, 45):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
        if quality == 65:
            img.thumbnail((int(long_side * 0.75),) * 2, Image.LANCZOS)
    return buf.getvalue()
