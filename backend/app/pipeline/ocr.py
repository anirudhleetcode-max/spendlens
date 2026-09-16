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
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from ..config import get_settings
from .preprocess import decode, preprocess

log = logging.getLogger(__name__)
DEFAULT_PSM = 6
OCR_TIMEOUT_S = 30  # per Tesseract call; a pathological image must not hang a worker


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


def run_tesseract(img: np.ndarray, psm: int = DEFAULT_PSM) -> list[OcrLine]:
    import pytesseract
    _configure_tesseract()
    data = pytesseract.image_to_data(img, lang="eng", config=f"--oem 1 --psm {psm} -c preserve_interword_spaces=1",
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
            want_preview: bool = False) -> dict:
    """Full image -> lines step. Raises ValueError for unreadable images.

    preprocess_enabled=False sends the plain grayscale photo to Tesseract (ablation baseline).
    dual=False only reads the thresholded image (ablation)."""
    t0 = time.perf_counter()
    img = decode(data)
    if not preprocess_enabled:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lines = run_tesseract(gray, psm)
        out = {"lines": lines, "mean_conf": mean_conf(lines), "skew": 0.0, "cropped": False,
               "variant": "raw", "steps_ms": {}, "ms": round((time.perf_counter() - t0) * 1000)}
        if want_preview:
            out["preview"] = _preview(gray, lines)
        return out
    prep = preprocess(img)
    # Adaptive threshold rescues shadows and uneven light but can eat faint thermal print; the denoised
    # grayscale keeps thin strokes. Read both (two tesseract processes in parallel) and keep the read
    # Tesseract itself is more confident about.
    if dual:
        with ThreadPoolExecutor(max_workers=2) as pool:
            bin_f = pool.submit(run_tesseract, prep.binary, psm)
            gray_f = pool.submit(run_tesseract, prep.gray, psm)
            reads = {"binary": bin_f.result(), "gray": gray_f.result()}
    else:
        reads = {"binary": run_tesseract(prep.binary, psm)}
    variant = max(reads, key=lambda k: mean_conf(reads[k]))
    lines = reads[variant]
    out = {"lines": lines, "mean_conf": mean_conf(lines), "skew": prep.skew, "cropped": prep.cropped,
           "variant": variant, "steps_ms": prep.steps_ms, "ms": round((time.perf_counter() - t0) * 1000)}
    if want_preview:
        out["preview"] = _preview(prep.binary if variant == "binary" else prep.gray, lines)
    return out


# backwards-compatible name used by earlier scripts
ocr_image = run_ocr
