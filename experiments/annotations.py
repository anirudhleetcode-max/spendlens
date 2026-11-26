"""Manually annotated ground truth: your own receipts, checked by a person.

Layout: data/annotations/<set>/<id>.json, one file per receipt:

    {"id": "bill_001",
     "image": "path/to/photo.jpg",          # relative to the repo root, or absolute (private photos stay outside git)
     "fields": {"merchant": "DMart", "date": "2026-09-01", "total": "497.00", "tax": "23.64",
                "payment_mode": "Cash", "category": "Groceries"},   # null = not on the receipt / not labelled
     "transcription": ["DMART", "AVENUE SUPERMARTS LTD", ...],         # every printed line, top to bottom
     "annotator": "...", "annotated_on": "YYYY-MM-DD",
     "verified": true}                       # only verified files are evaluated

Workflow:

    python -m experiments.annotations draft --images ~/bills --set mybills   # OCR pre-fills drafts
    # open each data/annotations/mybills/*.json, correct every field and line against the photo,
    # set "verified": true
    python -m experiments.annotations check --set mybills                    # schema + sanity checks
    python -m experiments.run --config experiments/configs/annotated_samples.yaml   # (copy, change dataset)

Transcription rules (so CER / WER mean the same thing across annotators):
  - one entry per printed line, top to bottom; left and right columns of one row on the same line,
    separated by one space
  - copy exactly what is printed (case, punctuation, `Rs.`, `@2.5%`), including typos on the receipt
  - leave out decorative separator rows (`-----`, `=====`), logos and barcodes; they are not text
  - fields hold the true values even when the print is unclear (read it from context or the arithmetic)

Drafts come from the pipeline under test, so an annotator who accepts them unchanged would bias the
evaluation towards the pipeline. `check` therefore reports how many drafts were never edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

from . import ROOT

ANN = ROOT / "data" / "annotations"
FIELD_KEYS = ("merchant", "date", "total", "tax", "payment_mode", "category")


def set_dir(name: str) -> Path:
    return ANN / name


def _image_path(p: str) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else ROOT / path


def load_annotated(name: str, include_unverified: bool = False):
    """Records in the common shape used by experiments/receipts_eval.py."""
    d = set_dir(name)
    if not d.exists():
        raise FileNotFoundError(f"No annotation set at {d}. Create one with `python -m experiments.annotations draft`.")
    for f in sorted(d.glob("*.json")):
        a = json.loads(f.read_text())
        if not a.get("verified") and not include_unverified:
            continue
        flds = a.get("fields") or {}
        yield {"id": a["id"], "image": _image_path(a["image"]).read_bytes(), "source": f"annotated:{name}",
               "fields": {"merchant": flds.get("merchant"), "date": flds.get("date"), "total": flds.get("total"),
                          "tax": flds.get("tax"), "payment_mode": flds.get("payment_mode"),
                          "category": flds.get("category"), "address": None, "n_items": None},
               "gt_lines": a.get("transcription") or None,
               "synthetic": bool(a.get("synthetic_image"))}


def set_info(name: str) -> dict:
    files = sorted(set_dir(name).glob("*.json"))
    h = hashlib.sha256()
    synth, verified = 0, 0
    for f in files:
        h.update(f.read_bytes())
        a = json.loads(f.read_text())
        synth += bool(a.get("synthetic_image"))
        verified += bool(a.get("verified"))
    return {"name": f"annotated:{name}", "title": f"Manually annotated set '{name}' (data/annotations/{name})",
            "sha256": h.hexdigest(), "licence": "own data", "n_files": len(files), "n_verified": verified,
            "synthetic": synth == len(files) and synth > 0, "n_synthetic_images": synth,
            "region": "India (target domain)"}


# ---------- draft / check ----------

def _fingerprint(a: dict) -> str:
    return hashlib.sha256(json.dumps([a.get("fields"), a.get("transcription")], sort_keys=True).encode()).hexdigest()[:16]


def draft(images: Path, name: str) -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.pipeline.ocr import run_ocr
    from app.pipeline.receipt import parse_lines
    out = set_dir(name)
    out.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for p in images.expanduser().iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    for p in paths:
        dest = out / f"{p.stem}.json"
        if dest.exists():
            print(f"skip {dest.name} (exists)")
            continue
        r = run_ocr(p.read_bytes())
        parsed = parse_lines(r["lines"])
        f = parsed["fields"]
        try:
            img = str(p.resolve().relative_to(ROOT))
        except ValueError:
            img = str(p.resolve())
        a = {"id": p.stem, "image": img,
             "fields": {"merchant": f["merchant"]["value"] or None, "date": f["date"]["value"],
                        "total": None if f["total"]["value"] is None else f"{f['total']['value']:.2f}",
                        "tax": None if not f["tax"]["value"] else f"{f['tax']['value']:.2f}",
                        "payment_mode": f["payment_mode"]["value"], "category": None},
             "transcription": [ln.text for ln in r["lines"]],
             "annotator": "DRAFT pre-filled by OCR - correct every field and every line against the photo",
             "annotated_on": date.today().isoformat(), "verified": False}
        a["draft_fingerprint"] = _fingerprint(a)
        dest.write_text(json.dumps(a, indent=2, ensure_ascii=False) + "\n")
        print(f"draft {dest.relative_to(ROOT)}")


def check(name: str) -> int:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.categories import CATEGORIES, PAYMENT_MODES
    problems, n, verified, untouched = [], 0, 0, 0
    for f in sorted(set_dir(name).glob("*.json")):
        n += 1
        try:
            a = json.loads(f.read_text())
        except ValueError as e:
            problems.append(f"{f.name}: not valid JSON ({e})"); continue
        verified += bool(a.get("verified"))
        if a.get("draft_fingerprint") and a["draft_fingerprint"] == _fingerprint(a) and a.get("verified"):
            untouched += 1
            problems.append(f"{f.name}: verified but identical to the OCR draft - was it really checked?")
        if not _image_path(a.get("image", "")).exists():
            problems.append(f"{f.name}: image not found: {a.get('image')}")
        flds = a.get("fields") or {}
        for k in flds:
            if k not in FIELD_KEYS:
                problems.append(f"{f.name}: unknown field {k!r}")
        if flds.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", flds["date"]):
            problems.append(f"{f.name}: date must be ISO YYYY-MM-DD, got {flds['date']!r}")
        for k in ("total", "tax"):
            if flds.get(k) is not None and not re.fullmatch(r"\d+(\.\d{1,2})?", str(flds[k])):
                problems.append(f"{f.name}: {k} must be a plain number like 1444.00, got {flds[k]!r}")
        if flds.get("category") and flds["category"] not in CATEGORIES:
            problems.append(f"{f.name}: category {flds['category']!r} not in {CATEGORIES}")
        if flds.get("payment_mode") and flds["payment_mode"] not in PAYMENT_MODES:
            problems.append(f"{f.name}: payment_mode {flds['payment_mode']!r} not in {PAYMENT_MODES}")
        if not a.get("transcription"):
            problems.append(f"{f.name}: no transcription (needed for CER / WER)")
    print(f"{name}: {n} files, {verified} verified, {untouched} verified-but-unedited drafts")
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--images", required=True, type=Path)
    d.add_argument("--set", required=True)
    c = sub.add_parser("check")
    c.add_argument("--set", required=True)
    a = ap.parse_args()
    if a.cmd == "draft":
        draft(a.images, a.set)
    else:
        sys.exit(check(a.set))


if __name__ == "__main__":
    main()
