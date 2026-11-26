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
  precision    correct / predicted (a filled-in wrong value counts against precision AND recall)
  recall       correct / labelled  (= exact accuracy over the labelled receipts)
  f1           harmonic mean of the two
  auto_*       the same, counting only values the UI accepts without asking (conf >= review threshold):
               what a user who never opens the review screen would get
Amounts (total, and tax where labelled):
  within_1pct  |pred - label| <= 1% of label, abs_error_median  (how far off the wrong ones are)
Dates: exact ISO match, plus day/month swapped count.
OCR quality (when ground-truth text exists):
  cer          character error rate = Levenshtein(pred, gt) / len(gt) on casefolded,
               whitespace-collapsed text, lines joined top to bottom (order errors count)
  wer          word error rate = word-level Levenshtein(pred words, gt words) / len(gt words)
  word_recall  share of ground-truth word tokens found in the OCR output (order-free)
Confidence usefulness:
  for the total: accuracy of fields the UI would *not* flag (conf >= review threshold) vs flagged ones.
Latency (per receipt, measured on the first, uncached OCR run): decode, preprocess, tesseract, parse;
  mean, p50, p95.
Category (annotated sets only): accuracy of the classifier's suggestion and of what it would store
  (abstentions -> Uncategorised).

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

OCR_DEFAULTS = {"oem": 1, "threshold": "adaptive_gaussian", "denoise": "nlmeans", "deskew": True}


def ocr_key(ocr_cfg: dict) -> str:
    key = f"pre{int(ocr_cfg.get('preprocess', True))}-dual{int(ocr_cfg.get('dual', True))}-psm{ocr_cfg.get('psm', 6)}"
    for k, default in OCR_DEFAULTS.items():  # only non-default settings, so old cache paths stay valid
        if k in ocr_cfg and ocr_cfg[k] != default:
            key += f"-{k}{ocr_cfg[k] if not isinstance(ocr_cfg[k], bool) else int(ocr_cfg[k])}"
    return key


def ocr_kwargs(ocr_cfg: dict) -> dict:
    return {"preprocess_enabled": ocr_cfg.get("preprocess", True), "psm": ocr_cfg.get("psm", 6),
            "dual": ocr_cfg.get("dual", True), **{k: ocr_cfg.get(k, v) for k, v in OCR_DEFAULTS.items()}}


def cached_ocr(dataset: str, rec: dict, ocr_cfg: dict, tag: str = ""):
    """tag: extra cache-path component for transformed images (the image-quality study)."""
    from app.pipeline.ocr import OcrLine, OcrWord, run_ocr
    path = CACHE / dataset.replace(":", "_") / ocr_key(ocr_cfg) / (f"{tag}/" if tag else "") / f"{rec['id']}.json"
    d = None
    if path.exists():
        try:
            d = json.loads(path.read_text())
        except ValueError:  # half-written by an interrupted run: recompute
            d = None
    if d is None:
        t = time.perf_counter()
        try:
            r = run_ocr(rec["image"], **ocr_kwargs(ocr_cfg))
            d = {"lines": [{"text": l.text, "conf": l.conf} for l in r["lines"]], "mean_conf": r["mean_conf"],
                 "variant": r["variant"], "skew": r["skew"], "cropped": r["cropped"],
                 "seconds": round(time.perf_counter() - t, 2), "timing_ms": r["timing_ms"],
                 "quality": {k: v for k, v in r["quality"].items() if k != "issues"} |
                            {"issues": [i["code"] for i in r["quality"]["issues"]]},
                 "error": None}
        except Exception as e:  # unreadable image: count it, don't crash the run
            d = {"lines": [], "mean_conf": 0, "variant": None, "skew": 0, "cropped": False,
                 "seconds": round(time.perf_counter() - t, 2), "timing_ms": None, "quality": None,
                 "error": str(e)[:200]}
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
    for i, (img, t, text) in enumerate(generate(n, seed, with_lines=True)):
        out.append({"id": f"synth-{seed}-{i:03d}", "image": img, "source": "synthetic",
                    "fields": {"merchant": t.merchant, "date": t.date, "total": f"{t.total:.2f}",
                               "tax": f"{t.tax:.2f}" if t.tax else None, "payment_mode": t.payment_mode,
                               "category": t.category,
                               "address": None, "n_items": len(t.items)},
                    "gt_lines": text})
    return out


# ---------- scoring ----------

def wer(pred: str, gt: str) -> float:
    """Word error rate: (substitutions + insertions + deletions) / number of ground-truth words."""
    g = gt.split()
    return Levenshtein.distance(pred.split(), g) / max(1, len(g))


def cer(pred: str, gt: str) -> float:
    return Levenshtein.distance(pred, gt) / max(1, len(gt))


def _amount_row(pred, label, conf, threshold) -> dict:
    want = label_total(label)
    exact = pred is not None and want is not None and abs(pred - want) < 0.005
    r = {"exact": exact, "normalised": exact or (pred is not None and total_digits(pred) == total_digits(label)),
         "filled": pred is not None, "conf": conf, "flagged": conf < threshold}
    if pred is not None and want:
        r["abs_error"] = round(abs(pred - want), 2)
        r["within_1pct"] = abs(pred - want) <= 0.01 * want + 0.005
    else:
        r["within_1pct"] = False
    return r


def score_one(rec: dict, parsed: dict, ocr: dict, threshold: float, category: dict | None = None) -> tuple[dict, list[dict]]:
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

    def err(field, expected, got):
        errors.append({"field": field, "expected": expected, "got": got,
                       "confidence": f[field]["confidence"], "source": f[field].get("source"),
                       "ocr_snippet": snippet(f[field].get("line"))})

    if lab.get("merchant"):
        pred = f["merchant"]["value"] or ""
        row["merchant"] = {"exact": norm_text(pred) == norm_text(lab["merchant"]),
                           "normalised": alnum(pred) == alnum(lab["merchant"]) and bool(alnum(pred)),
                           "partial": fuzz.ratio(norm_text(pred), norm_text(lab["merchant"])) >= 80,
                           "filled": bool(pred), "conf": f["merchant"]["confidence"]}
        if not row["merchant"]["partial"]:
            err("merchant", lab["merchant"], pred)
    if lab.get("date"):
        want = label_date(lab["date"])
        pred = f["date"]["value"]
        swapped = False
        if pred and want and pred != want:
            y, m, d = want.split("-")
            swapped = pred == f"{y}-{d}-{m}"
        row["date"] = {"exact": want is not None and pred == want, "normalised": want is not None and pred == want,
                       "filled": pred is not None, "conf": f["date"]["confidence"], "label_parsed": want is not None,
                       "day_month_swapped": swapped}
        if not row["date"]["exact"]:
            err("date", lab["date"], pred)
    if lab.get("total"):
        row["total"] = _amount_row(f["total"]["value"], lab["total"], f["total"]["confidence"], threshold)
        if not row["total"]["exact"]:
            err("total", lab["total"], f["total"]["value"])
    if lab.get("tax") is not None:
        pred = f["tax"]["value"] if f["tax"]["source"] != "none" else None
        row["tax"] = _amount_row(pred, lab["tax"], f["tax"]["confidence"], threshold)
        if not row["tax"]["exact"]:
            err("tax", lab["tax"], pred)
    if lab.get("payment_mode"):
        pred = f["payment_mode"]["value"]
        pred = None if pred == "Unknown" else pred
        row["payment_mode"] = {"exact": pred == lab["payment_mode"], "filled": pred is not None,
                               "conf": f["payment_mode"]["confidence"]}
        if not row["payment_mode"]["exact"]:
            err("payment_mode", lab["payment_mode"], pred)
    if lab.get("category") and category is not None:
        row["category"] = {"exact": category["category"] == lab["category"],
                           "stored_exact": category["stored"] == lab["category"],
                           "filled": not category["abstained"], "conf": category["confidence"],
                           "abstained": category["abstained"]}
    if lab.get("n_items") is not None:
        row["items"] = {"count_exact": len(parsed["items"]) == lab["n_items"]}
    if rec.get("gt_lines"):
        gt = norm_text(" ".join(rec["gt_lines"]))
        pr = norm_text(" ".join(l["text"] for l in ocr["lines"]))
        row["cer"] = cer(pr, gt)
        row["wer"] = wer(pr, gt)
        gt_words = Counter(gt.split())
        pr_words = Counter(pr.split())
        row["word_recall"] = sum((gt_words & pr_words).values()) / max(1, sum(gt_words.values()))
    row["ocr_seconds"] = ocr["seconds"]
    row["timing_ms"] = dict(ocr.get("timing_ms") or {}) | {"parse": parsed.get("_parse_ms")}
    row["quality"] = ocr.get("quality")
    row["mean_conf"] = ocr.get("mean_conf")
    row["n_corrections"] = len(parsed.get("corrections") or [])
    row["ocr_error"] = ocr["error"]
    for e in errors:
        e["id"] = rec["id"]
    return row, errors


def _ratio(a, b):
    return round(a / b, 4) if b else None


def prf(rs: list[dict], threshold: float | None = None) -> dict:
    """Field-level precision / recall / F1 over receipts that have a label for the field."""
    ok = lambda r: r["filled"] and (threshold is None or r["conf"] >= threshold)  # noqa: E731
    pred = sum(ok(r) for r in rs)
    correct = sum(ok(r) and r["exact"] for r in rs)
    p, rec = _ratio(correct, pred), _ratio(correct, len(rs))
    f1 = round(2 * p * rec / (p + rec), 4) if p and rec else 0.0
    return {"precision": p, "recall": rec, "f1": f1, "tp": correct, "fp": pred - correct, "fn": len(rs) - correct}


def pctl(xs: list[float], q: float):
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))
    return round(xs[i], 1)


SCORED_FIELDS = ("merchant", "date", "total", "tax", "payment_mode", "category")


def summarise(rows: list[dict], threshold: float = 0.6) -> dict:
    out: dict = {"n_receipts": len(rows)}
    for fld in SCORED_FIELDS:
        rs = [r[fld] for r in rows if fld in r]
        if not rs:
            continue
        m = {"n_labelled": len(rs)}
        for k in ("exact", "normalised", "partial", "filled", "within_1pct", "stored_exact"):
            if k in rs[0]:
                m[k if k != "filled" else "coverage"] = round(sum(r[k] for r in rs) / len(rs), 4)
        m |= prf(rs)
        m["auto"] = prf(rs, threshold)
        if fld in ("total", "tax"):
            errs = sorted(r["abs_error"] for r in rs if r.get("abs_error") and not r["exact"])
            m["abs_error_median_when_wrong"] = errs[len(errs) // 2] if errs else None
            un = [r for r in rs if not r["flagged"]]
            fl = [r for r in rs if r["flagged"]]
            m["accuracy_when_not_flagged"] = _ratio(sum(r["exact"] for r in un), len(un))
            m["accuracy_when_flagged"] = _ratio(sum(r["exact"] for r in fl), len(fl))
            m["share_flagged"] = round(len(fl) / len(rs), 4)
        if fld == "date":
            m["labels_unparseable"] = sum(not r["label_parsed"] for r in rs)
            m["day_month_swapped"] = sum(r["day_month_swapped"] for r in rs)
        if fld == "category":
            m["abstained"] = round(sum(r["abstained"] for r in rs) / len(rs), 4)
        out[fld] = m
    it = [r["items"] for r in rows if "items" in r]
    if it:
        out["items"] = {"n_labelled": len(it), "count_exact": round(sum(r["count_exact"] for r in it) / len(it), 4)}
    with_gt = [r for r in rows if "cer" in r]
    if with_gt:
        c = sorted(r["cer"] for r in with_gt)
        w = sorted(r["wer"] for r in with_gt)
        out["ocr"] = {"cer_mean": round(sum(c) / len(c), 4), "cer_median": round(c[len(c) // 2], 4),
                      "wer_mean": round(sum(w) / len(w), 4), "wer_median": round(w[len(w) // 2], 4),
                      "word_recall_mean": round(sum(r["word_recall"] for r in with_gt) / len(with_gt), 4)}
    out["ocr_seconds_mean"] = round(sum(r["ocr_seconds"] for r in rows) / max(1, len(rows)), 2)
    lat = {}
    for stage in ("decode", "preprocess", "ocr", "parse"):
        xs = [r["timing_ms"][stage] for r in rows if (r.get("timing_ms") or {}).get(stage) is not None]
        if xs:
            lat[stage] = {"mean": round(sum(xs) / len(xs), 1), "p50": pctl(xs, 0.5), "p95": pctl(xs, 0.95)}
    tot = [sum(v for v in (r.get("timing_ms") or {}).values() if v is not None) for r in rows
           if (r.get("timing_ms") or {}).get("ocr") is not None]
    if tot:
        lat["total"] = {"mean": round(sum(tot) / len(tot), 1), "p50": pctl(tot, 0.5), "p95": pctl(tot, 0.95),
                        "max": round(max(tot), 1)}
    out["latency_ms"] = lat
    out["corrections_per_receipt"] = round(sum(r.get("n_corrections", 0) for r in rows) / max(1, len(rows)), 2)
    out["ocr_failures"] = sum(1 for r in rows if r["ocr_error"])
    return out


def suggest_category(parsed: dict) -> dict:
    """The classifier the API uses, without the per-user override lookup (no database here)."""
    from app.categories import UNCATEGORISED
    from app.services.classifier import build_text, get_model
    model = get_model()
    pred = model.predict(build_text(parsed["fields"]["merchant"]["value"] or "", [i["name"] for i in parsed["items"]]))
    if pred is None:
        return {"category": UNCATEGORISED, "confidence": 0.0, "abstained": True, "stored": UNCATEGORISED}
    abstain = pred["p"] < model.threshold
    return {"category": pred["top"], "confidence": round(pred["p"], 3), "abstained": abstain,
            "stored": UNCATEGORISED if abstain else pred["top"]}


def evaluate(records: list[dict], dataset: str, ocr_cfg: dict, progress: bool = True,
             parser_cfg: dict | None = None, tag: str = "") -> tuple[dict, list[dict], list[dict]]:
    from app.pipeline.confidence import REVIEW_THRESHOLD
    from app.pipeline.receipt import parse_lines
    rows, errors = [], []
    t0 = time.time()
    want_category = any(r["fields"].get("category") for r in records)
    for i, rec in enumerate(records):
        ocr = cached_ocr(dataset, rec, ocr_cfg, tag)
        tp = time.perf_counter()
        parsed = parse_lines(ocr["lines_obj"], **(parser_cfg or {}))
        parsed["_parse_ms"] = round((time.perf_counter() - tp) * 1000, 2)
        category = suggest_category(parsed) if want_category else None
        row, errs = score_one(rec, parsed, ocr, REVIEW_THRESHOLD, category)
        rows.append(row)
        errors += errs
        if progress and (i + 1) % 20 == 0:
            print(f"  [{ocr_key(ocr_cfg)}] {i + 1}/{len(records)}  {time.time() - t0:.0f}s", flush=True)
    summary = summarise(rows, REVIEW_THRESHOLD)
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
