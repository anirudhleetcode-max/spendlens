"""OCR on generated receipt photos. Needs Tesseract; skipped (with a reason) when it is missing."""
import cv2
import numpy as np
import pytest

from app.services.ocr import decode, estimate_skew, find_document, ocr_image, rotate, tesseract_version
from app.services.parser import parse_receipt
from app.utils import merchant_key
from ml.receipts_synth import SHOPS, generate, make_receipt, render

needs_tesseract = pytest.mark.skipif(tesseract_version() is None, reason="Tesseract not installed")


def _clean_receipt_gray(seed=1):
    import random
    rng = random.Random(seed)
    lines, _ = make_receipt(rng, SHOPS[0])
    return cv2.cvtColor(np.asarray(render(lines, rng, clean=True)), cv2.COLOR_RGB2GRAY)


@pytest.mark.parametrize("angle", [-6.0, -2.5, 0.0, 3.0, 7.0])
def test_deskew_recovers_rotation(angle):
    gray = _clean_receipt_gray()
    tilted = rotate(gray, angle)
    est = estimate_skew(tilted)
    assert abs(est + angle) < 0.5, est          # estimate is the correction to apply
    assert abs(estimate_skew(rotate(tilted, est))) < 0.5


def test_find_document_on_photo():
    img_bytes, _ = generate(1, seed=5)[0]
    img = decode(img_bytes)
    corners = find_document(img)
    assert corners is not None
    h, w = img.shape[:2]
    area = cv2.contourArea(corners.astype(np.float32))
    assert 0.3 * h * w < area < 0.95 * h * w


def test_decode_rejects_garbage():
    with pytest.raises(ValueError):
        decode(b"not an image")


@needs_tesseract
def test_parse_accuracy_on_generated_receipts():
    data = generate(6, seed=7)
    hits = {"merchant": 0, "date": 0, "total": 0}
    for img, truth in data:
        out = parse_receipt(ocr_image(img)["lines"])["fields"]
        hits["merchant"] += merchant_key(out["merchant"]["value"]) == merchant_key(truth.merchant)
        hits["date"] += out["date"]["value"] == truth.date
        hits["total"] += out["total"]["value"] is not None and abs(out["total"]["value"] - truth.total) < 0.01
    # tolerance: allow one miss per field out of six
    assert all(v >= 5 for v in hits.values()), hits
