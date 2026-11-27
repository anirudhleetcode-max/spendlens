"""Stage 1 - image preprocessing.

decode (EXIF-aware, pixel-limit guarded) -> resize (long side <= 2000 px, short side >= 900 px)
-> perspective crop of the largest 4-point contour, when the paper is visible against a background
-> grayscale -> non-local-means denoise -> deskew (text-line blobs + minAreaRect, Hough fallback)
-> adaptive Gaussian threshold.

Alternatives for the denoise and threshold steps (median / bilateral / Gaussian; Otsu / Sauvola / mean)
are selectable for experiments; the defaults are the production choice. `image_quality()` measures
blur, contrast, brightness and noise so the app can ask for a retake.

Every step is a small pure function on numpy arrays so it can be unit-tested and ablated.
Bump PREPROCESS_VERSION whenever the output of `preprocess()` changes; it is written into model cards
and experiment results.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps

PREPROCESS_VERSION = "1.0"
# Decompression-bomb guard: a 30 MP phone photo is fine, a 20000x20000 PNG "zip bomb" is not.
# Pillow raises DecompressionBombError above 2x this value and warns above it; we refuse above it.
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

def decode(data: bytes) -> np.ndarray:
    """Bytes -> BGR array, honouring phone EXIF rotation."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ValueError(f"Image is too large ({img.width}x{img.height} px). Limit is {MAX_PIXELS // 1_000_000} MP.")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except ValueError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError(f"Image is too large. Limit is {MAX_PIXELS // 1_000_000} MP.")
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


def normalize_contrast(gray: np.ndarray, low_pct: float = 1.0, high_pct: float = 99.0) -> np.ndarray:
    """Stretch grey levels so the 1st percentile becomes 0 and the 99th 255. Faded thermal print and dark
    photos otherwise leave ink only a few grey levels from the paper, and NL-means (fixed strength h)
    then smooths the text away. Experimental, off by default: it fixed faded and dark synthetic photos but
    raised CER on real SROIE scans (0.165 -> 0.194) and CORD photos (0.403 -> 0.487); see
    experiments/reports/ocr_quality.md, section 4."""
    lo, hi = np.percentile(gray, [low_pct, high_pct])
    if hi - lo < 8:  # blank page: nothing to stretch
        return gray
    out = (gray.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------- denoising and thresholding (selectable, so experiments can compare them) ----------

DENOISE_METHODS = ("nlmeans", "nlmeans_adaptive", "median", "bilateral", "gaussian", "none")
THRESHOLD_METHODS = ("adaptive_gaussian", "adaptive_mean", "otsu", "sauvola", "none")


def denoise(gray: np.ndarray, method: str = "nlmeans") -> np.ndarray:
    """Noise removal on a grayscale image.

    nlmeans    non-local means with a fixed strength h=12: averages similar patches, keeps edges sharp
    nlmeans_adaptive  the same with h = 1.5 x the measured noise sigma, clamped to [4, 30]: light on clean
               or faint print (which a fixed h smooths away), strong on grainy low-light photos
    median     3x3 median: removes salt-and-pepper specks, can close thin gaps in 0/8/6
    bilateral  edge-preserving smoothing; cheaper than NL-means, weaker on sensor noise
    gaussian   3x3 Gaussian blur: removes noise and softens edges
    none       pass-through (ablation)"""
    if method == "nlmeans":
        return cv2.fastNlMeansDenoising(gray, None, h=12, templateWindowSize=7, searchWindowSize=15)
    if method == "nlmeans_adaptive":
        h = float(np.clip(1.5 * noise_sigma(gray), 4.0, 30.0))
        return cv2.fastNlMeansDenoising(gray, None, h=h, templateWindowSize=7, searchWindowSize=15)
    if method == "median":
        return cv2.medianBlur(gray, 3)
    if method == "bilateral":
        return cv2.bilateralFilter(gray, 7, 50, 7)
    if method == "gaussian":
        return cv2.GaussianBlur(gray, (3, 3), 0)
    if method == "none":
        return gray
    raise ValueError(f"unknown denoise method {method!r}; choose from {DENOISE_METHODS}")


def sauvola(gray: np.ndarray, window: int = 31, k: float = 0.2, r: float = 128.0) -> np.ndarray:
    """Sauvola local threshold T = m * (1 + k * (s / r - 1)) with mean m and std s over a window.
    Good for uneven lighting and faded print; computed with box filters (O(1) per pixel)."""
    g = gray.astype(np.float64)
    mean = cv2.boxFilter(g, -1, (window, window), borderType=cv2.BORDER_REPLICATE)
    sq = cv2.boxFilter(g * g, -1, (window, window), borderType=cv2.BORDER_REPLICATE)
    std = np.sqrt(np.maximum(sq - mean * mean, 0))
    t = mean * (1 + k * (std / r - 1))
    return np.where(g > t, 255, 0).astype(np.uint8)


def threshold(gray: np.ndarray, method: str = "adaptive_gaussian") -> np.ndarray:
    """Binarisation: black text on white.

    adaptive_gaussian  Gaussian-weighted local mean - C over a 31 px window (production)
    adaptive_mean      plain local mean - C
    otsu               one global threshold that best separates the two histogram modes; fails on shadows
    sauvola            local mean and contrast (document-binarisation classic)
    none               keep grayscale (Tesseract binarises internally with Otsu)"""
    if method == "adaptive_gaussian":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    if method == "adaptive_mean":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 15)
    if method == "otsu":
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    if method == "sauvola":
        return sauvola(gray)
    if method == "none":
        return gray
    raise ValueError(f"unknown threshold method {method!r}; choose from {THRESHOLD_METHODS}")


# ---------- image quality ----------

# Limits for the retake hints, set from the degradation study (experiments/reports/ocr_quality.md, section 4):
# each sits where extraction accuracy starts to collapse, not where the image merely looks worse. Contrast
# and brightness only flag extreme cases: real receipts with little ink read fine at low RMS contrast. Motion blur, shadows
# and heavy JPEG are not visible to these measures; the OCR-confidence hint (OCR_CONF_MIN) catches them.
# No over-exposure limit: a clean scan is mostly white paper (SROIE median mean brightness 239), so mean
# brightness cannot tell glare from paper; glare that washes out text shows up as low OCR confidence.
QUALITY_LIMITS = {"sharpness_min": 10.0, "contrast_min": 10.0, "brightness_min": 30.0,
                  "short_side_min": 300, "noise_max": 20.0}
OCR_CONF_MIN = 60.0  # Tesseract mean word confidence; below it 79% of SROIE totals were wrong (vs 37% above)

def noise_sigma(gray: np.ndarray) -> float:
    """Immerkaer's fast noise estimate: std of a Laplacian-difference kernel that cancels smooth
    structure. Gives sigma in grey levels for additive Gaussian noise."""
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float64)
    h, w = gray.shape
    conv = cv2.filter2D(gray.astype(np.float64), -1, k, borderType=cv2.BORDER_REFLECT)
    return float(np.sum(np.abs(conv[1:-1, 1:-1])) * np.sqrt(0.5 * np.pi) / (6 * (w - 2) * (h - 2)))


def image_quality(img: np.ndarray) -> dict:
    """Cheap, reference-free quality measures of the photo as uploaded.

    sharpness   variance of the Laplacian on a 1000 px-wide copy (low = blurred / out of focus)
    contrast    RMS contrast = std of grey levels (low = faded thermal print, fog, glare)
    brightness  mean grey level (low = dark photo, high = overexposed)
    noise       Immerkaer noise sigma (high = grainy low-light photo)
    issues      the measures outside QUALITY_LIMITS, as user-facing hints"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = gray.shape
    scale = 1000 / w
    norm = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    q = {"width": int(w), "height": int(h),
         "sharpness": round(float(cv2.Laplacian(norm, cv2.CV_64F).var()), 1),
         "contrast": round(float(gray.std()), 1),
         "brightness": round(float(gray.mean()), 1),
         "noise": round(noise_sigma(norm), 2)}
    q["issues"] = quality_issues(q)
    return q


def quality_issues(q: dict, mean_conf: float | None = None) -> list[dict]:
    """User-facing retake hints from image_quality() measures and, after OCR, Tesseract's mean confidence."""
    L = QUALITY_LIMITS
    issues = []
    if q["sharpness"] < L["sharpness_min"] and q["noise"] < L["noise_max"]:  # noise inflates the Laplacian
        issues.append({"code": "blurry", "message": "The photo looks blurred. Hold the phone steady and tap to focus."})
    if q["contrast"] < L["contrast_min"]:
        issues.append({"code": "low_contrast", "message": "The print is very faint. Try more even light."})
    if q["brightness"] < L["brightness_min"]:
        issues.append({"code": "dark", "message": "The photo is very dark. Move to better light."})
    if min(q["height"], q["width"]) < L["short_side_min"]:
        issues.append({"code": "low_resolution", "message": "The photo is small. Move closer so the bill fills the frame."})
    if q["noise"] > L["noise_max"]:
        issues.append({"code": "noisy", "message": "The photo is grainy. More light will help."})
    if mean_conf is not None and mean_conf < OCR_CONF_MIN:
        issues.append({"code": "ocr_unsure", "message": f"The text was hard to read (OCR confidence {mean_conf:.0f}%). "
                       "A sharper, flatter, evenly lit photo will help; check every field."})
    return issues


@dataclass
class Prepared:
    gray: np.ndarray
    binary: np.ndarray
    skew: float
    cropped: bool
    steps_ms: dict = field(default_factory=dict)


def preprocess(img: np.ndarray, crop: bool = True, denoise_method: str = "nlmeans",
               threshold_method: str = "adaptive_gaussian", deskew: bool = True, normalize: bool = False) -> Prepared:
    """Defaults are the production pipeline; the keyword arguments exist for experiments."""
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
    if normalize:
        gray = normalize_contrast(gray)
    gray = denoise(gray, denoise_method); tick("denoise")
    skew = estimate_skew(gray) if deskew else 0.0
    if abs(skew) > 0.3:
        gray = rotate(gray, skew)
    tick("deskew")
    # no median blur afterwards: it closes the inner stroke of slashed/dotted zeros (0 -> 6/8)
    binary = threshold(gray, threshold_method)
    tick("threshold")
    return Prepared(gray=gray, binary=binary, skew=round(skew, 2), cropped=cropped, steps_ms=ms)
