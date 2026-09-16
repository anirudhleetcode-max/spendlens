"""Evaluate OCR + field extraction on labelled receipts (real: SROIE, CORD; or synthetic).

Metrics (per field, over the receipts that have a label for that field):
  exact        merchant: equal after whitespace-collapse + casefold
               date:     predicted ISO date == label parsed day-first (the label format varies)
               total:    |pred - label| < 0.005
  normalised   merchant: equal after keeping only [a-z0-9]
               total:    digit strings equal after dropping separators and a trailing ".00"
                         (credits "60.000" IDR == 60000 and "193.00" == 193)
  partial      merchant: rapidfuzz ratio >= 80 (so "Ojc Marketing" vs "OJC MARKETING SDN BHD" is visible)
  coverage     share of receipts where the field was filled at all
OCR quality (when ground-truth text exists):
  cer          character error rate = Levenshtein(pred, gt) / len(gt) on casefolded,
               whitespace-collapsed text, lines joined top to bottom (order errors count)
  word_recall  share of ground-truth word tokens found in the OCR output (order-free)
Confidence usefulness:
  for the total: accuracy of fields the UI would *not* flag (conf >= review threshold) vs flagged ones.

OCR output is cached per (dataset, id, OCR settings) in data/cache/ so that parser-only changes can be
re-scored without re-running Tesseract. The parser itself is never tuned on these test sets.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from . import ROOT
from .datasets import load

CACHE = ROOT / "data" / "cache" / "ocr"
FIELDS = ("merchant", "date", "total")


# ---------- label normalisation ----------

def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").casefold())


def label_date(s: str | None) -> str | None:
    """SROIE dates: 15/01/2019, 25-03-2018, 2018-03-25, 12 MAR 2018, 03/13/2018 ... -> ISO."""
    if not s:
        return None
    from app.pipeline.normalise import find_dates
    found = find_dates(s)
    return found[0].isoformat() if found else None


def total_digits(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        s = f"{float(v):.2f}"
    else:
        s = re.sub(r"[^\d.,]", "", str(v))
    s = re.sub(r"[.,]00$", "", s)
    return re.sub(r"\D", "", s)


def label_total(s) -> float | None:
    if s in (None, ""):
        return None
    t = re.sub(r"[^\d.,]", "", str(s))
    m = re.fullmatch(r"(\d[\d,]*)\.(\d{2})", t)
    if m:
        return float(m.group(1).replace(",", "") + "." + m.group(2))
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


# ---------- OCR with cache ----------

def ocr_key(ocr_cfg: dict) -> str:
    return f"pre{int(ocr_cfg.get('preprocess', True))}-dual{int(ocr_cfg.get('dual', True))}-psm{ocr_cfg.get('psm', 6)}"


def cached_ocr(dataset: str, rec: dict, ocr_cfg: dict):
    from app.pipeline.ocr import OcrLine, OcrWord, run_ocr
    path = CACHE / dataset / ocr_key(ocr_cfg) / f"{rec['id']}.json"
    if path.exists():
        d = json.loads(path.read_text())
    else:
        t = time.perf_counter()
        try:
            r = run_ocr(rec["image"], preprocess_enabled=ocr_cfg.get("preprocess", True),
                        psm=ocr_cfg.get("psm", 6), dual=ocr_cfg.get("dual", True))
            d = {"lines": [{"text": l.text, "conf": l.conf} for l in r["lines"]], "mean_conf": r["mean_conf"],
                 "variant": r["variant"], "skew": r["skew"], "cropped": r["cropped"],
                 "seconds": round(time.perf_counter() - t, 2), "error": None}
        except Exception as e:  # unreadable image: count it, don't crash the run
            d = {"lines": [], "mean_conf": 0, "variant": None, "skew": 0, "cropped": False,
                 "seconds": round(time.perf_counter() - t, 2), "error": str(e)[:200]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d))
    d["lines_obj"] = [OcrLine(l["text"], l["conf"], []) for l in d["lines"]]
    _ = OcrWord  # boxes are not needed for scoring
    return d


def select(dataset: str, n: int | None, seed: int) -> list[dict]:
    """Deterministic subset: sort ids, sample n with the given seed (keeps images in memory)."""
    recs = sorted(load(dataset), key=lambda r: r["id"])
    if n and n < len(recs):
        keep = set(random.Random(seed).sample([r["id"] for r in recs], n))
        recs = [r for r in recs if r["id"] in keep]
    return recs


def synthetic_records(n: int, seed: int) -> list[dict]:
    from ml.receipts_synth import generate
    out = []
    for i, (img, t) in enumerate(generate(n, seed)):
        out.append({"id": f"synth-{seed}-{i:03d}", "image": img, "source": "synthetic",
                    "fields": {"merchant": t.merchant, "date": t.date, "total": f"{t.total:.2f}",
                               "address": None, "n_items": len(t.items)},
                    "gt_lines": None})
    return out


# ---------- scoring ----------

def score_one(rec: dict, parsed: dict, ocr: dict, threshold: float) -> tuple[dict, list[dict]]:
    f = parsed["fields"]
    lab = rec["fields"]
    row: dict = {"id": rec["id"]}
    errors = []

    def snippet(line_idx):
        lines = [l["text"] for l in ocr["lines"]]
        if line_idx is None:
            return " | ".join(lines[:4])[:240]
        lo = max(0, line_idx - 1)
        return " | ".join(lines[lo: line_idx + 2])[:240]

    if lab.get("merchant"):
        pred = f["merchant"]["value"] or ""
        row["merchant"] = {"exact": norm_text(pred) == norm_text(lab["merchant"]),
                           "normalised": alnum(pred) == alnum(lab["merchant"]) and bool(alnum(pred)),
                           "partial": fuzz.ratio(norm_text(pred), norm_text(lab["merchant"])) >= 80,
                           "filled": bool(pred), "conf": f["merchant"]["confidence"]}
        if not row["merchant"]["partial"]:
            errors.append({"field": "merchant", "expected": lab["merchant"], "got": pred,
                           "confidence": f["merchant"]["confidence"], "source": f["merchant"].get("source"),
                           "ocr_snippet": snippet(f["merchant"].get("line"))})
    if lab.get("date"):
        want = label_date(lab["date"])
        pred = f["date"]["value"]
        row["date"] = {"exact": want is not None and pred == want, "normalised": want is not None and pred == want,
                       "filled": pred is not None, "conf": f["date"]["confidence"], "label_parsed": want is not None}
        if not row["date"]["exact"]:
            errors.append({"field": "date", "expected": lab["date"], "got": pred,
                           "confidence": f["date"]["confidence"], "source": f["date"].get("source"),
                           "ocr_snippet": snippet(f["date"].get("line"))})
    if lab.get("total"):
        want = label_total(lab["total"])
        pred = f["total"]["value"]
        exact = pred is not None and want is not None and abs(pred - want) < 0.005
        row["total"] = {"exact": exact, "normalised": exact or (pred is not None and total_digits(pred) == total_digits(lab["total"])),
                        "filled": pred is not None, "conf": f["total"]["confidence"],
                        "flagged": f["total"]["confidence"] < threshold}
        if not exact:
            errors.append({"field": "total", "expected": lab["total"], "got": pred,
                           "confidence": f["total"]["confidence"], "source": f["total"].get("source"),
                           "ocr_snippet": snippet(f["total"].get("line"))})
    if lab.get("n_items") is not None:
        row["items"] = {"count_exact": len(parsed["items"]) == lab["n_items"]}
    if rec.get("gt_lines"):
        gt = norm_text(" ".join(rec["gt_lines"]))
        pr = norm_text(" ".join(l["text"] for l in ocr["lines"]))
        row["cer"] = Levenshtein.distance(pr, gt) / max(1, len(gt))
        gt_words = Counter(gt.split())
        pr_words = Counter(pr.split())
        row["word_recall"] = sum((gt_words & pr_words).values()) / max(1, sum(gt_words.values()))
    row["ocr_seconds"] = ocr["seconds"]
    row["ocr_error"] = ocr["error"]
    for e in errors:
        e["id"] = rec["id"]
    return row, errors


def summarise(rows: list[dict]) -> dict:
    out: dict = {"n_receipts": len(rows)}
    for fld in FIELDS:
        rs = [r[fld] for r in rows if fld in r]
        if not rs:
            continue
        m = {"n_labelled": len(rs)}
        for k in ("exact", "normalised", "partial", "filled"):
            if k in rs[0]:
                m[k if k != "filled" else "coverage"] = round(sum(r[k] for r in rs) / len(rs), 4)
        if fld == "total":
            un = [r for r in rs if not r["flagged"]]
            fl = [r for r in rs if r["flagged"]]
            m["accuracy_when_not_flagged"] = round(sum(r["exact"] for r in un) / len(un), 4) if un else None
            m["accuracy_when_flagged"] = round(sum(r["exact"] for r in fl) / len(fl), 4) if fl else None
            m["share_flagged"] = round(len(fl) / len(rs), 4)
        if fld == "date":
            m["labels_unparseable"] = sum(not r["label_parsed"] for r in rs)
        out[fld] = m
    it = [r["items"] for r in rows if "items" in r]
    if it:
        out["items"] = {"n_labelled": len(it), "count_exact": round(sum(r["count_exact"] for r in it) / len(it), 4)}
    cer = sorted(r["cer"] for r in rows if "cer" in r)
    if cer:
        out["ocr"] = {"cer_mean": round(sum(cer) / len(cer), 4), "cer_median": round(cer[len(cer) // 2], 4),
                      "word_recall_mean": round(sum(r["word_recall"] for r in rows if "word_recall" in r) / len(cer), 4)}
    out["ocr_seconds_mean"] = round(sum(r["ocr_seconds"] for r in rows) / max(1, len(rows)), 2)
    out["ocr_failures"] = sum(1 for r in rows if r["ocr_error"])
    return out


def evaluate(records: list[dict], dataset: str, ocr_cfg: dict, progress: bool = True,
             parser_cfg: dict | None = None) -> tuple[dict, list[dict], list[dict]]:
    from app.pipeline.confidence import REVIEW_THRESHOLD
    from app.pipeline.receipt import parse_lines
    rows, errors = [], []
    t0 = time.time()
    for i, rec in enumerate(records):
        ocr = cached_ocr(dataset, rec, ocr_cfg)
        parsed = parse_lines(ocr["lines_obj"], **(parser_cfg or {}))
        row, errs = score_one(rec, parsed, ocr, REVIEW_THRESHOLD)
        rows.append(row)
        errors += errs
        if progress and (i + 1) % 20 == 0:
            print(f"  [{ocr_key(ocr_cfg)}] {i + 1}/{len(records)}  {time.time() - t0:.0f}s", flush=True)
    summary = summarise(rows)
    summary["parser_version"] = parsed["parser_version"] if records else None
    return summary, rows, errors


def ids_hash(records: list[dict]) -> str:
    return hashlib.sha256("\n".join(r["id"] for r in records).encode()).hexdigest()[:16]


def write_errors(run_dir: Path, errors: list[dict], title: str, limit: int = 40) -> None:
    """Worst first: confidently wrong beats unsure-and-wrong (those are the ones the UI won't flag)."""
    errors = sorted(errors, key=lambda e: -(e.get("confidence") or 0))
    with open(run_dir / "errors.jsonl", "w") as f:
        for e in errors:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    by_field = Counter(e["field"] for e in errors)
    lines = [f"# Worst parse failures - {title}", "",
             f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. {len(errors)} field errors "
             f"({', '.join(f'{k}: {v}' for k, v in by_field.most_common())}). Sorted by confidence, highest first.",
             "", "| image id | field | expected | got | conf | source | OCR snippet |", "|---|---|---|---|---|---|---|"]
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    for e in errors[:limit]:
        lines.append(f"| {e['id']} | {e['field']} | {esc(e['expected'])} | {esc(e['got'])} | "
                     f"{e['confidence']:.2f} | {esc(e.get('source'))} | {esc(e['ocr_snippet'])[:140]} |")
    (run_dir / "errors.md").write_text("\n".join(lines) + "\n")
