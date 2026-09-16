"""Measure end-to-end receipt parsing on generated receipt photos.

    python -m ml.eval_ocr --n 30

Runs every receipt twice - through the full OpenCV preprocessing and straight into Tesseract - so the
effect of preprocessing is measured, not assumed. Results go to ml/metrics.json under "receipt_parsing".
"""
from __future__ import annotations

import argparse
import time

from app.pipeline.ocr import run_ocr as ocr_image, tesseract_version
from app.pipeline.receipt import parse_lines as parse_receipt
from app.utils import merchant_key
from ml.receipts_synth import generate
from ml.train_classifier import update_metrics


def score(pred: dict, truth) -> dict:
    f = pred["fields"]
    total = f["total"]["value"]
    return {
        "merchant": merchant_key(f["merchant"]["value"] or "") == merchant_key(truth.merchant),
        "date": f["date"]["value"] == truth.date,
        "total": total is not None and abs(total - truth.total) < 0.01,
        "tax": abs((f["tax"]["value"] or 0) - truth.tax) < 0.02,
        "payment_mode": f["payment_mode"]["value"] == truth.payment_mode,
        "item_count": len(pred["items"]) == len(truth.items),
    }


def run(n: int, seed: int) -> dict:
    if not tesseract_version():
        raise SystemExit("Tesseract not found - see README (TESSERACT_CMD)")
    data = generate(n, seed)
    report = {}
    for variant, pre in [("with_preprocessing", True), ("raw_tesseract", False)]:
        hits: dict[str, int] = {}
        secs = []
        failures = []
        for i, (img, truth) in enumerate(data):
            t = time.perf_counter()
            ocr = ocr_image(img, preprocess_enabled=pre)
            pred = parse_receipt(ocr["lines"])
            secs.append(time.perf_counter() - t)
            s = score(pred, truth)
            for k, v in s.items():
                hits[k] = hits.get(k, 0) + int(v)
            wrong = [k for k in ("merchant", "date", "total") if not s[k]]
            if wrong and len(failures) < 8:
                failures.append({"i": i, "merchant": truth.merchant, "wrong": wrong,
                                 "got": {k: pred["fields"][k]["value"] for k in wrong},
                                 "want": {"merchant": truth.merchant, "date": truth.date, "total": truth.total}})
        report[variant] = {
            "exact_match": {k: round(v / n, 3) for k, v in hits.items()},
            "all_three_correct": None,
            "mean_seconds": round(sum(secs) / n, 2),
            "failures_sample": failures,
        }
        print(variant, report[variant]["exact_match"], f"{report[variant]['mean_seconds']}s/receipt")
    return {"n_receipts": n, "seed": seed, "tesseract": tesseract_version(),
            "note": "synthetic thermal receipts (ml/receipts_synth.py): rotation +-4 deg, blur, noise, "
                    "background; real phone photos are harder",
            **report}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    res = run(a.n, a.seed)
    for k in ("with_preprocessing", "raw_tesseract"):
        res[k].pop("all_three_correct")
    update_metrics("receipt_parsing", res)


if __name__ == "__main__":
    main()
