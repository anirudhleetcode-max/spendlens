"""Stage orchestration: OCR lines -> reviewed receipt fields.

    preprocess.py -> ocr.py -> correct.py -> normalise.py -> extract.py -> validate.py -> confidence.py
    -> (category: app/services/classifier.py) -> record (routers/expenses.py)
"""
from __future__ import annotations

from datetime import date, datetime

from .confidence import REVIEW_THRESHOLD
from .correct import correct_lines
from .extract import (extract_date, extract_items, extract_merchant, extract_payment, extract_tax,
                      extract_total)
from .validate import run_checks

PARSER_VERSION = "1.3"  # 1.2: tax-inclusive total lines are total candidates
#                        1.3: OCR-error correction (correct.py); total fallback skips cash-tendered / change lines


def parse_lines(lines, legacy_total_rule: bool = False, correct_ocr: bool = True, version: str | None = None) -> dict:
    """Pure function of the OCR lines; used by the API, the tests and the evaluation scripts.
    For before/after comparisons: version="1.2" reproduces parser 1.2, legacy_total_rule=True parser 1.1,
    correct_ocr=False is 1.3 without the OCR-error correction (ablation)."""
    if version == "1.2" or legacy_total_rule:
        correct_ocr = False
    skip_tendered = version != "1.2" and not legacy_total_rule
    corrections: list[dict] = []
    if correct_ocr:
        lines, corrections = correct_lines(lines)
    fields = {
        "merchant": extract_merchant(lines),
        "date": extract_date(lines),
        "total": extract_total(lines, tax_inclusive_rule=not legacy_total_rule, skip_tendered=skip_tendered),
        "tax": extract_tax(lines),
        "payment_mode": extract_payment(lines),
    }
    items = extract_items(lines)
    fields, checks = run_checks(fields, items, lines)
    for it in items:
        if it["price"] is None:  # fuel slip: the litres row costs the whole bill
            it["price"] = fields["total"].value or 0.0
    return {"fields": {k: v.as_dict() for k, v in fields.items()}, "items": items, "checks": checks,
            "review_threshold": REVIEW_THRESHOLD, "corrections": corrections,
            "parser_version": "1.1" if legacy_total_rule else ("1.2" if version == "1.2" else
                                                              PARSER_VERSION + ("" if correct_ocr else "-nocorrect"))}


# backwards-compatible name
parse_receipt = parse_lines


def parsed_date_or_today(value: str | None) -> date:
    try:
        return datetime.fromisoformat(value).date() if value else date.today()
    except ValueError:
        return date.today()
