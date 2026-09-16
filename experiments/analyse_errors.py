"""Group the receipt-extraction errors of a run into causes (counts are written next to errors.jsonl).

    python -m experiments.analyse_errors experiments/results/sroie_main-20260916

Causes (heuristic, checked by reading examples):
  merchant  lexicon_false_match  an Indian lexicon entry matched a different company
            wrong_header_line    first name-like header line was not the company (person, 'COPY', logo text)
            not_found            no name-like line in the first six
            ocr_garbled          right line, but the company name was misread (fuzzy ratio 60-79)
  date      ocr_digit            predicted date differs from the label in one digit (misread)
            wrong_date_line      a different date on the receipt was picked (expiry, print time)
            not_found            no parseable date
  total     not_found | fallback_largest  |  ocr_digit (same length, 1-2 digits differ)
            wrong_keyword_line   a total-like line that is not the payable total (e.g. 'Total 0% supplies')
            amount_format        digits right, separators wrong (CORD '60.000')
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz

from .receipts_eval import label_date, label_total, total_digits


def digits_close(a: str, b: str) -> bool:
    return len(a) == len(b) and 0 < sum(x != y for x, y in zip(a, b)) <= 2


def cause(e: dict) -> str:
    f, got, exp, src = e["field"], e["got"], e["expected"], (e.get("source") or "")
    if f == "merchant":
        if not got:
            return "not_found"
        if src == "lexicon":
            return "lexicon_false_match"
        return "ocr_garbled" if fuzz.partial_ratio(got.lower(), exp.lower()) >= 60 else "wrong_header_line"
    if f == "date":
        if not got:
            return "not_found"
        want = label_date(exp) or ""
        return "ocr_digit" if digits_close(re.sub(r"\D", "", got), re.sub(r"\D", "", want)) else "wrong_date_line"
    if got is None:
        return "not_found"
    if total_digits(got) == total_digits(exp) or (label_total(exp) and got * 1000 == label_total(exp)):
        return "amount_format"
    if src.startswith("fallback"):
        return "fallback_largest"
    if digits_close(f"{got:.2f}", f"{(label_total(exp) or 0):.2f}"):
        return "ocr_digit"
    return "wrong_keyword_line"


def main(run_dir: str) -> None:
    d = Path(run_dir)
    errors = [json.loads(line) for line in open(d / "errors.jsonl")]
    by = {}
    for e in errors:
        by.setdefault(e["field"], Counter())[cause(e)] += 1
    confident = Counter(e["field"] for e in errors if (e.get("confidence") or 0) >= 0.6)
    out = {"n_errors": len(errors), "by_field_and_cause": {k: dict(v.most_common()) for k, v in by.items()},
           "confidently_wrong_(conf>=0.6)": dict(confident)}
    (d / "errors_breakdown.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
