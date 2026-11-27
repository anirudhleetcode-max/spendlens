"""Stage 2 - optical character recognition (Tesseract 5, LSTM engine).

`run_ocr()` is the whole image -> text step used by the API and by the evaluation scripts:
  preprocess (optional) -> Tesseract on the thresholded image and on the denoised grayscale, in
  parallel -> keep the read with the higher mean word confidence.
Tesseract returns words with boxes and a 0-100 confidence; words are grouped into lines by
(block, paragraph, line). Boxes are kept (normalised to 0-1) for the OCR preview in the UI.

PSM (page segmentation mode) 6 = "a single uniform block of text" suits a receipt column; 4 and 11
are compared in experiments/configs/sroie_ablation.yaml.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from ..config import get_settings
from .preprocess import decode, image_quality, preprocess

log = logging.getLogger(__name__)
DEFAULT_PSM = 6
DEFAULT_OEM = 1
# Per Tesseract call; a pathological image must not hang a worker. Raise it on slow shared
# CPUs (Render's free instance needs more than 30 s for a full-size photo).
OCR_TIMEOUT_S = float(os.getenv("OCR_TIMEOUT_S", "30"))
# Tesseract uses OpenMP and starts one busy-waiting thread per core. run_ocr() already runs two tesseract
# processes in parallel, so on small machines (2-CPU CI runners, shared cloud instances) the threads starve
# each other and calls hit the timeout. One thread per process is also faster for page-sized images.
# The subprocess inherits this; an explicit setting in the environment wins.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")


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


@dataclass
class OcrWord:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int


@dataclass
class OcrLine:
    text: str
    conf: float  # 0-100 mean word confidence
    words: list[OcrWord] = field(default_factory=list)


def run_tesseract(img: np.ndarray, psm: int = DEFAULT_PSM, oem: int = DEFAULT_OEM) -> list[OcrLine]:
    """oem 1 = LSTM neural engine (production); 0 = legacy pattern matcher; 2 = both combined.
    0 and 2 need the legacy model in eng.traineddata (present in the full `tessdata`, not in `tessdata_fast`)."""
    import pytesseract
    _configure_tesseract()
    data = pytesseract.image_to_data(img, lang="eng", config=f"--oem {oem} --psm {psm} -c preserve_interword_spaces=1",
                                     output_type=pytesseract.Output.DICT, timeout=OCR_TIMEOUT_S)
    groups: dict[tuple, list[OcrWord]] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append(OcrWord(word, conf, data["left"][i], data["top"][i],
                                                  data["width"][i], data["height"][i]))
    lines = []
    for key in sorted(groups):
        words = sorted(groups[key], key=lambda w: w.left)
        lines.append(OcrLine(text=" ".join(w.text for w in words),
                             conf=round(sum(w.conf for w in words) / len(words), 1), words=words))
    return lines


def mean_conf(lines: list[OcrLine]) -> float:
    return round(sum(l.conf for l in lines) / len(lines), 1) if lines else 0.0


def _preview(img: np.ndarray, lines: list[OcrLine], width: int = 720) -> dict:
    """Small JPEG of exactly what Tesseract read + word boxes normalised to [0, 1]."""
    h, w = img.shape[:2]
    scale = min(1.0, width / w)
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
    buf = io.BytesIO()
    Image.fromarray(small).save(buf, "JPEG", quality=70)
    boxes = [{"x": round(wd.left / w, 4), "y": round(wd.top / h, 4), "w": round(wd.width / w, 4),
              "h": round(wd.height / h, 4), "conf": round(wd.conf), "text": wd.text}
             for ln in lines for wd in ln.words]
    return {"image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "width": small.shape[1], "height": small.shape[0], "boxes": boxes[:1500]}


def run_ocr(data: bytes, preprocess_enabled: bool = True, psm: int = DEFAULT_PSM, dual: bool = True,
            want_preview: bool = False, oem: int = DEFAULT_OEM, threshold: str = "adaptive_gaussian",
            denoise: str = "nlmeans", deskew: bool = True, normalize: bool = False) -> dict:
    """Full image -> lines step. Raises ValueError for unreadable images.

    preprocess_enabled=False sends the plain grayscale photo to Tesseract (ablation baseline).
    dual=False only reads the thresholded image (ablation). oem / threshold / denoise / deskew select
    alternatives for the OCR-configuration comparison; the defaults are production.
    `timing_ms` splits the latency into decode, preprocess and tesseract."""
    t0 = time.perf_counter()
    img = decode(data)
    t_dec = time.perf_counter()
    quality = image_quality(img)
    if not preprocess_enabled:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        t_pre = time.perf_counter()
        lines = run_tesseract(gray, psm, oem)
        t_ocr = time.perf_counter()
        out = {"lines": lines, "mean_conf": mean_conf(lines), "skew": 0.0, "cropped": False,
               "variant": "raw", "steps_ms": {}, "quality": quality, "ms": round((t_ocr - t0) * 1000),
               "timing_ms": _timing(t0, t_dec, t_pre, t_ocr)}
        if want_preview:
            out["preview"] = _preview(gray, lines)
        return out
    prep = preprocess(img, denoise_method=denoise, threshold_method=threshold, deskew=deskew, normalize=normalize)
    t_pre = time.perf_counter()
    # Adaptive threshold rescues shadows and uneven light but can eat faint thermal print; the denoised
    # grayscale keeps thin strokes. Read both (two tesseract processes in parallel) and keep the read
    # Tesseract itself is more confident about.
    if dual and threshold != "none":
        with ThreadPoolExecutor(max_workers=2) as pool:
            bin_f = pool.submit(run_tesseract, prep.binary, psm, oem)
            gray_f = pool.submit(run_tesseract, prep.gray, psm, oem)
            reads = {"binary": bin_f.result(), "gray": gray_f.result()}
    elif threshold == "none":
        reads = {"gray": run_tesseract(prep.gray, psm, oem)}
    else:
        reads = {"binary": run_tesseract(prep.binary, psm, oem)}
    t_ocr = time.perf_counter()
    variant = max(reads, key=lambda k: mean_conf(reads[k]))
    lines = reads[variant]
    out = {"lines": lines, "mean_conf": mean_conf(lines), "skew": prep.skew, "cropped": prep.cropped,
           "variant": variant, "steps_ms": prep.steps_ms, "quality": quality,
           "ms": round((t_ocr - t0) * 1000), "timing_ms": _timing(t0, t_dec, t_pre, t_ocr)}
    if want_preview:
        out["preview"] = _preview(prep.binary if variant == "binary" else prep.gray, lines)
    return out


def _timing(t0: float, t_dec: float, t_pre: float, t_ocr: float) -> dict:
    return {"decode": round((t_dec - t0) * 1000, 1), "preprocess": round((t_pre - t_dec) * 1000, 1),
            "ocr": round((t_ocr - t_pre) * 1000, 1)}


# backwards-compatible name used by earlier scripts
ocr_image = run_ocr
