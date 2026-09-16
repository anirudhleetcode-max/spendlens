"""Receipt image -> text lines with confidences.

Pipeline (each step is a small pure function so it can be unit-tested and explained):
  decode (EXIF-aware) -> resize -> perspective crop of the largest 4-point contour (if any)
  -> grayscale -> denoise -> deskew (text-line blobs + minAreaRect, Hough fallback)
  -> adaptive threshold -> Tesseract (image_to_data, word confidences) -> lines
"""
from __future__ import annotations

import io
import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..config import get_settings

log = logging.getLogger(__name__)


# ---------- tesseract availability ----------

def _configure_tesseract() -> None:
    import pytesseract
    cmd = get_settings().tesseract_cmd.strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


@lru_cache
def tesseract_version() -> str | None:
    """Cached: None when Tesseract is not installed / not found."""
    try:
        import pytesseract
        _configure_tesseract()
        return str(pytesseract.get_tesseract_version())
    except Exception as e:  # TesseractNotFoundError, ImportError, OSError
        log.warning("Tesseract not available: %s (set TESSERACT_CMD in .env)", e)
        return None


def ocr_status() -> dict:
    v = tesseract_version()
    return {"available": v is not None, "version": v,
            "cmd": get_settings().tesseract_cmd or shutil.which("tesseract") or None}


# ---------- image steps ----------

def decode(data: bytes) -> np.ndarray:
    """Bytes -> BGR array, honouring phone EXIF rotation."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise ValueError("Could not read the image. Upload a JPG, PNG or WebP photo.")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def resize_for_ocr(img: np.ndarray, target_long: int = 2000, min_short: int = 900) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(target_long / max(h, w), 1.0)
    if min(h, w) * scale < min_short:  # tiny photo: upscale so glyphs are ~30px tall
        scale = min(min_short / min(h, w), 2.5)
    if abs(scale - 1.0) < 0.02:
        return img
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def find_document(img: np.ndarray) -> np.ndarray | None:
    """Largest convex 4-point contour covering 20-97% of the frame (the paper), or None."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small_scale = 600 / max(gray.shape)
    small = cv2.resize(gray, None, fx=small_scale, fy=small_scale, interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (5, 5), 0)
    edges = cv2.Canny(small, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_total = small.shape[0] * small.shape[1]
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        a = cv2.contourArea(approx)
        if len(approx) == 4 and cv2.isContourConvex(approx) and 0.2 * area_total < a < 0.97 * area_total:
            return _order_corners(approx / small_scale)
    return None


def perspective_crop(img: np.ndarray, corners: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = corners
    w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    M = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def estimate_skew(gray: np.ndarray) -> float:
    """Angle (degrees) the text lines are tilted by. Text is smeared horizontally into line blobs;
    the median minAreaRect angle of long thin blobs is the skew. Falls back to Hough lines."""
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    blobs = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, gray.shape[1] // 40), 3)))
    contours, _ = cv2.findContours(blobs, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles, weights = [], []
    for c in contours:
        rect = cv2.minAreaRect(c)
        (w, h) = rect[1]
        if max(w, h) < gray.shape[1] * 0.15 or max(w, h) < 4 * min(w, h):
            continue  # not a text line
        # angle of the long edge, measured directly (OpenCV changed minAreaRect's angle convention in 4.5)
        p = cv2.boxPoints(rect)
        e1, e2 = p[1] - p[0], p[2] - p[1]
        dx, dy = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
        a = float(np.degrees(np.arctan2(dy, dx)))
        while a > 90:
            a -= 180
        while a <= -90:
            a += 180
        if abs(a) <= 45:
            angles.append(a); weights.append(max(w, h))
    if len(angles) >= 3:
        order = np.argsort(angles)
        cum = np.cumsum(np.array(weights)[order])
        return float(np.array(angles)[order][np.searchsorted(cum, cum[-1] / 2)])  # weighted median
    lines = cv2.HoughLinesP(bw, 1, np.pi / 180, 100, minLineLength=gray.shape[1] // 4, maxLineGap=10)
    if lines is None:
        return 0.0
    deg = [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in lines[:, 0]]
    deg = [d for d in deg if abs(d) < 20]
    return float(np.median(deg)) if deg else 0.0


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, M, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


@dataclass
class Prepared:
    gray: np.ndarray
    binary: np.ndarray
    skew: float
    cropped: bool
    steps_ms: dict = field(default_factory=dict)


def preprocess(img: np.ndarray, crop: bool = True) -> Prepared:
    t = time.perf_counter()
    ms = {}

    def tick(name):
        nonlocal t
        now = time.perf_counter(); ms[name] = round((now - t) * 1000); t = now

    img = resize_for_ocr(img); tick("resize")
    cropped = False
    if crop:
        corners = find_document(img)
        if corners is not None:
            img = perspective_crop(img, corners); cropped = True
        tick("crop")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, h=12, templateWindowSize=7, searchWindowSize=15); tick("denoise")
    skew = estimate_skew(gray)
    if abs(skew) > 0.3:
        gray = rotate(gray, skew)
    tick("deskew")
    # no median blur afterwards: it closes the inner stroke of slashed/dotted zeros (0 -> 6/8)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    tick("threshold")
    return Prepared(gray=gray, binary=binary, skew=round(skew, 2), cropped=cropped, steps_ms=ms)


# ---------- OCR ----------

@dataclass
class OcrLine:
    text: str
    conf: float  # 0-100 mean word confidence


def run_tesseract(img: np.ndarray, psm: int = 6) -> list[OcrLine]:
    import pytesseract
    _configure_tesseract()
    data = pytesseract.image_to_data(img, lang="eng", config=f"--oem 1 --psm {psm} -c preserve_interword_spaces=1",
                                     output_type=pytesseract.Output.DICT)
    groups: dict[tuple, list[tuple[str, float, int]]] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append((word, conf, data["left"][i]))
    lines = []
    for key in sorted(groups):
        words = sorted(groups[key], key=lambda w: w[2])
        text = " ".join(w[0] for w in words)
        lines.append(OcrLine(text=text, conf=round(sum(w[1] for w in words) / len(words), 1)))
    return lines


def mean_conf(lines: list[OcrLine]) -> float:
    return round(sum(l.conf for l in lines) / len(lines), 1) if lines else 0.0


def ocr_image(data: bytes, preprocess_enabled: bool = True) -> dict:
    """Full pipeline. Returns lines + diagnostics. Raises ValueError for unreadable images."""
    t0 = time.perf_counter()
    img = decode(data)
    if not preprocess_enabled:
        lines = run_tesseract(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        return {"lines": lines, "mean_conf": mean_conf(lines), "skew": 0.0, "cropped": False,
                "variant": "raw", "ms": round((time.perf_counter() - t0) * 1000)}
    prep = preprocess(img)
    # Adaptive threshold rescues shadows and uneven light but can eat faint thermal print; the denoised
    # grayscale keeps thin strokes. Read both (two tesseract processes in parallel) and keep the read
    # Tesseract itself is more confident about.
    with ThreadPoolExecutor(max_workers=2) as pool:
        bin_f = pool.submit(run_tesseract, prep.binary)
        gray_f = pool.submit(run_tesseract, prep.gray)
        reads = {"binary": bin_f.result(), "gray": gray_f.result()}
    variant = max(reads, key=lambda k: mean_conf(reads[k]))
    lines = reads[variant]
    return {"lines": lines, "mean_conf": mean_conf(lines), "skew": prep.skew, "cropped": prep.cropped,
            "variant": variant, "steps_ms": prep.steps_ms, "ms": round((time.perf_counter() - t0) * 1000)}
