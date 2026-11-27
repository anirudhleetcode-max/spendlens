"""How does image quality affect OCR and extraction? Controlled degradations + measured quality.

Two questions:
1. Degradation study - take receipts whose ground truth is known, damage each image in one controlled way
   at increasing severity, and re-run the whole pipeline. One corruption at a time, so each curve shows
   one cause. Every receipt is its own control (same receipt clean vs damaged).
2. Do the reference-free quality measures (app.pipeline.preprocess.image_quality) predict failure?
   Spearman correlation of each measure with CER and with total-correct, over every image scored,
   and the accuracy of totals for images the app would ask to retake vs not.

Corruptions model what phone photos of thermal bills actually suffer from:
    gaussian_blur  out of focus              sigma (px at ~1000 px width)
    motion_blur    hand shake                kernel length (px)
    noise          low light sensor noise    sigma (grey levels)
    jpeg           messaging-app recompress  JPEG quality
    downscale      far away / small photo    scale factor
    low_contrast   faded thermal print       contrast kept (1 = original)
    dark           dim room                  brightness kept
    shadow         phone/hand shadow         shadow depth across the bill
    rotation       tilted shot               degrees
Degraded images are re-encoded losslessly (PNG) except for the jpeg corruption.
"""
from __future__ import annotations

import io
import random
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image

CORRUPTIONS: dict[str, list[float]] = {
    "gaussian_blur": [1.0, 2.0, 3.0, 4.5],
    "motion_blur": [5, 11, 17, 25],
    "noise": [10, 20, 35, 55],
    "jpeg": [40, 20, 10, 5],
    "downscale": [0.7, 0.5, 0.35, 0.25],
    "low_contrast": [0.6, 0.4, 0.25, 0.15],
    "dark": [0.7, 0.5, 0.35, 0.22],
    "shadow": [0.3, 0.5, 0.7, 0.85],
    "rotation": [3, 8, 15, 25],
}


def _decode(data: bytes) -> np.ndarray:
    from app.pipeline.preprocess import decode
    return decode(data)


def _encode(img: np.ndarray, jpeg_quality: int | None = None) -> bytes:
    buf = io.BytesIO()
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if jpeg_quality:
        pil.save(buf, "JPEG", quality=int(jpeg_quality))
    else:
        pil.save(buf, "PNG", compress_level=1)
    return buf.getvalue()


def _scale_px(img: np.ndarray, v: float) -> float:
    """Severities are defined for a ~1000 px wide image; scale them to this image's width."""
    return v * img.shape[1] / 1000


def degrade(data: bytes, kind: str, level: float, seed: int = 0) -> bytes:
    img = _decode(data)
    rng = np.random.default_rng(seed)
    if kind == "gaussian_blur":
        s = _scale_px(img, level)
        out = cv2.GaussianBlur(img, (0, 0), s)
    elif kind == "motion_blur":
        k = max(3, int(round(_scale_px(img, level))) | 1)
        kern = np.zeros((k, k), np.float32)
        kern[k // 2, :] = 1.0 / k
        rot = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), float(rng.uniform(-30, 30)), 1.0)
        kern = cv2.warpAffine(kern, rot, (k, k))
        kern /= max(kern.sum(), 1e-6)
        out = cv2.filter2D(img, -1, kern)
    elif kind == "noise":
        out = np.clip(img.astype(np.float32) + rng.normal(0, level, img.shape[:2])[..., None], 0, 255).astype(np.uint8)
    elif kind == "jpeg":
        return _encode(img, jpeg_quality=int(level))
    elif kind == "downscale":
        out = cv2.resize(img, None, fx=level, fy=level, interpolation=cv2.INTER_AREA)
    elif kind == "low_contrast":
        f = img.astype(np.float32)
        out = np.clip(200 + (f - 200) * level, 0, 255).astype(np.uint8)  # fade towards paper white-grey
    elif kind == "dark":
        out = np.clip(img.astype(np.float32) * level, 0, 255).astype(np.uint8)
    elif kind == "shadow":
        h, w = img.shape[:2]
        ang = rng.uniform(0, np.pi)
        xs, ys = np.meshgrid(np.linspace(-1, 1, w), np.linspace(-1, 1, h))
        proj = xs * np.cos(ang) + ys * np.sin(ang)
        mask = 1 - level * (1 / (1 + np.exp(-proj * 6)))  # soft-edged shadow over one side
        out = np.clip(img.astype(np.float32) * mask[..., None], 0, 255).astype(np.uint8)
    elif kind == "rotation":
        from app.pipeline.preprocess import rotate
        sign = 1 if rng.random() < 0.5 else -1
        out = rotate(img, sign * level)
    else:
        raise ValueError(kind)
    return _encode(out)


def conditions(cfg: dict) -> list[tuple[str, float | None]]:
    kinds = cfg.get("corruptions") or list(CORRUPTIONS)
    out: list[tuple[str, float | None]] = [("clean", None)]
    for k in kinds:
        out += [(k, lv) for lv in CORRUPTIONS[k]]
    return out


def prefill(records, dataset, ocr_cfg, tag, workers):
    """Run uncached OCR in parallel (tesseract is a subprocess; OpenCV releases the GIL)."""
    from .receipts_eval import cached_ocr
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda r: cached_ocr(dataset, r, ocr_cfg, tag), records))


def spearman(x, y) -> float | None:
    from scipy.stats import spearmanr
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 5 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return round(float(spearmanr(x, y).statistic), 3)


def quality_correlations(rows: list[dict]) -> dict:
    """rows: per-receipt score rows that carry `quality` (and optionally cer / total)."""
    rows = [r for r in rows if r.get("quality")]
    out = {"n_images": len(rows)}
    for target in ("cer", "wer"):
        sub = [r for r in rows if target in r]
        if sub:
            out[f"spearman_vs_{target}"] = {m: spearman([r["quality"][m] for r in sub], [r[target] for r in sub])
                                            for m in ("sharpness", "contrast", "brightness", "noise")}
            out[f"spearman_vs_{target}"]["tesseract_mean_conf"] = spearman([r["mean_conf"] for r in sub],
                                                                          [r[target] for r in sub])
    sub = [r for r in rows if "total" in r]
    if sub:
        out["spearman_vs_total_correct"] = {m: spearman([r["quality"][m] for r in sub],
                                                        [float(r["total"]["exact"]) for r in sub])
                                            for m in ("sharpness", "contrast", "brightness", "noise")}
        # hints recomputed from the stored measures with the current limits (cached `issues` may be older)
        from app.pipeline.preprocess import quality_issues
        hint = {id(r): [i["code"] for i in quality_issues(r["quality"], r.get("mean_conf"))] for r in sub}
        flagged = [r for r in sub if hint[id(r)]]
        ok = [r for r in sub if not hint[id(r)]]
        acc = lambda rs: round(sum(r["total"]["exact"] for r in rs) / len(rs), 4) if rs else None  # noqa: E731
        out["retake_hint"] = {"share_flagged": round(len(flagged) / len(sub), 4),
                              "total_accuracy_flagged": acc(flagged), "total_accuracy_not_flagged": acc(ok),
                              "issue_counts": _count([i for r in flagged for i in hint[id(r)]])}
    return out


def _count(xs):
    out: dict = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def rescore(run_dir) -> dict:
    """Recompute quality_vs_errors for a finished run from per_image.jsonl (e.g. after changing the limits)."""
    import json
    from pathlib import Path
    rows = [json.loads(line) for line in open(Path(run_dir) / "per_image.jsonl")]
    return {v: quality_correlations([r for r in rows if r["variant"] == v]) for v in dict.fromkeys(r["variant"] for r in rows)}


def run_quality(cfg: dict, run_dir, load_records) -> dict:
    """Task `image_quality` (see experiments/configs/quality_*.yaml)."""
    import json
    from .receipts_eval import evaluate
    records, info = load_records(cfg)
    workers = int(cfg.get("workers", 2))
    out = {"dataset": info | {"n_selected": len(records)}, "workers": workers,
           "note": "Latency is not comparable here: images were OCR'd several at a time.",
           "variants": {}}
    all_rows = []
    for var in cfg["variants"]:
        curves: dict = {}
        for kind, level in conditions(cfg):
            tag = "clean" if kind == "clean" else f"{kind}-{level}"
            seeded = [(i, r) for i, r in enumerate(records)]
            imgs = [r if kind == "clean" else r | {"image": degrade(r["image"], kind, level, seed=i)}
                    for i, r in seeded]
            t = time.time()
            prefill(imgs, info["name"], var["ocr"], tag, workers)
            summary, rows, _ = evaluate(imgs, info["name"], var["ocr"], progress=False,
                                        parser_cfg=var.get("parser"), tag=tag)
            for r in rows:
                r["condition"] = tag
                r["variant"] = var["name"]
            all_rows += rows
            keep = {k: summary.get(k) for k in ("merchant", "date", "total", "ocr")}
            curves.setdefault(kind, []).append(
                {"level": level, "cer": (keep["ocr"] or {}).get("cer_mean"), "wer": (keep["ocr"] or {}).get("wer_mean"),
                 "merchant": (keep["merchant"] or {}).get("exact"), "date": (keep["date"] or {}).get("exact"),
                 "total": (keep["total"] or {}).get("exact"),
                 "total_auto_precision": ((keep["total"] or {}).get("auto") or {}).get("precision"),
                 "total_flagged": (keep["total"] or {}).get("share_flagged"),
                 "mean_quality": _mean_quality(rows), "seconds": round(time.time() - t, 1)})
            c = curves[kind][-1]
            print(f"  [{var['name']}] {tag:22} cer={c['cer']} total={c['total']} date={c['date']}", flush=True)
        out["variants"][var["name"]] = {"ocr_settings": var["ocr"], "curves": curves}
    out["quality_vs_errors"] = {v["name"]: quality_correlations([r for r in all_rows if r["variant"] == v["name"]])
                                for v in cfg["variants"]}
    with open(run_dir / "per_image.jsonl", "w") as f:
        for r in all_rows:
            f.write(json.dumps(r) + "\n")
    return out


def _mean_quality(rows):
    qs = [r["quality"] for r in rows if r.get("quality")]
    if not qs:
        return None
    return {m: round(sum(q[m] for q in qs) / len(qs), 1) for m in ("sharpness", "contrast", "brightness", "noise")} | \
           {"share_with_issues": round(sum(bool(q["issues"]) for q in qs) / len(qs), 3)}


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
