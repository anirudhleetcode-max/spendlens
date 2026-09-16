"""Stage 5 - validation: does the receipt agree with itself?

Checks (each returns a dict {id, status, field, message}; status is pass | warn | fail | info):
- total_arithmetic  subtotal + tax + round-off (or rate x litres on fuel slips) vs the total. If they
                    disagree, the total is retried with commonly confused digits swapped (thermal "0"
                    read as "6"/"8"); a variant that makes the bill add up replaces it, flagged.
- total_source      the total came from the "largest amount" fallback, not a total line.
- total_missing     no amount found at all.
- date_missing      no plausible date (future / impossible dates are rejected upstream).
- merchant_unknown  merchant name is a guess from the header, not a lexicon match.
- items_sum         line items vs the printed subtotal.
"""
from __future__ import annotations

import re

from . import confidence as C
from .extract import Field
from .normalise import decimal_amounts, inr

CONFUSABLE = {"6": "0", "8": "0", "9": "0", "0": "8", "5": "6", "3": "8", "1": "7", "7": "1"}


def check(id_: str, status: str, field: str, message: str) -> dict:
    return {"id": id_, "status": status, "field": field, "message": message}


def digit_variants(value: float) -> set[float]:
    """Totals with one or two commonly-confused digits swapped."""
    s = f"{value:.2f}"
    out = set()
    idx = [i for i, c in enumerate(s) if c in CONFUSABLE]
    for a in idx:
        one = s[:a] + CONFUSABLE[s[a]] + s[a + 1:]
        out.add(float(one))
        for b in idx:
            if b > a:
                out.add(float(one[:b] + CONFUSABLE[one[b]] + one[b + 1:]))
    return out


def round_off(lines) -> float:
    for ln in lines:
        if re.search(r"round\s*-?\s*off|rounding", ln.text, re.I):
            m = re.search(r"([+-]?)\s*(\d+)[.,](\d{2})\s*$", ln.text)
            if m:
                v = float(f"{m.group(2)}.{m.group(3)}")
                return -v if m.group(1) == "-" else v
    return 0.0


def subtotal(lines) -> float | None:
    for ln in lines:
        if re.search(r"sub\s*-?\s*tota", ln.text, re.I):
            vals = decimal_amounts(ln.text)
            if vals:
                return vals[-1]
    return None


def expected_total(lines, tax: float) -> tuple[float, str] | None:
    """What the receipt's own arithmetic says the total should be, and how that was worked out."""
    sub = subtotal(lines)
    if sub is not None:
        ro = round_off(lines)
        parts = [f"subtotal {inr(sub)}", f"tax {inr(tax or 0)}"] + ([f"round-off {ro:+.2f}"] if ro else [])
        return sub + (tax or 0) + ro, " + ".join(parts)
    text = "\n".join(l.text for l in lines)
    rate = re.search(r"rate\s*/?\s*l\w*\s*[:\-]?\s*(\d+[.,]\d{2})", text, re.I)
    vol = re.search(r"(volume|vol)\s*(\(l\))?\s*[:\-]?\s*(\d+[.,]\d{1,3})", text, re.I)
    if rate and vol:
        r, v = float(rate.group(1).replace(",", ".")), float(vol.group(3).replace(",", "."))
        return r * v, f"rate {r:.2f}/L x {v} L"
    return None


def reconcile_total(total: Field, lines, tax: float) -> tuple[Field, dict | None]:
    exp = expected_total(lines, tax)
    if total.value is None or exp is None:
        return total, None
    expected, how = exp
    # with a round-off line the sum should be exact; without one it is within a rupee
    has_ro = round_off(lines) != 0
    keep_tol = 0.02 if has_ro else max(1.0, 0.005 * expected)
    repair_tol = 0.15 if has_ro else keep_tol  # a line item or subtotal may itself be off by a digit
    err = abs(total.value - expected)
    if err <= keep_tol:
        total.confidence = max(total.confidence, C.ARITH_AGREES_FLOOR)
        return total, check("total_arithmetic", "pass", "total",
                            f"Total {inr(total.value)} matches {how}.")
    best_err, best = min((abs(v - expected), v) for v in digit_variants(total.value))
    if best_err <= repair_tol and best_err < err:
        fixed = Field(round(best, 2), C.ARITH_REPAIRED, total.source + "+digit-repair", total.line)
        return fixed, check("total_arithmetic", "warn", "total",
                            f"Read {inr(total.value)}, but {how} = {inr(expected)}. "
                            f"Corrected to {inr(best)} - please check.")
    total.confidence = min(total.confidence, C.ARITH_DISAGREES_CAP)
    return total, check("total_arithmetic", "fail", "total",
                        f"Total {inr(total.value)} ≠ {how} = {inr(expected)}.")


def run_checks(fields: dict[str, Field], items: list[dict], lines) -> tuple[dict[str, Field], list[dict]]:
    checks: list[dict] = []
    fields["total"], arith = reconcile_total(fields["total"], lines, fields["tax"].value or 0)
    total = fields["total"]
    if total.value is None:
        checks.append(check("total_missing", "fail", "total", "No amount found on the bill. Enter the total."))
    elif total.source.startswith("fallback"):
        checks.append(check("total_source", "warn", "total",
                            "No 'Total' line found - used the largest amount on the bill."))
    if arith:
        checks.append(arith)
    if fields["date"].value is None:
        checks.append(check("date_missing", "warn", "date", "No date found - defaulted to today."))
    if fields["merchant"].source == "header":
        checks.append(check("merchant_unknown", "info", "merchant",
                            "Merchant isn't in our list - name taken from the top of the bill."))
    elif fields["merchant"].source == "none":
        checks.append(check("merchant_unknown", "warn", "merchant", "Couldn't find the merchant name."))
    sub = subtotal(lines)
    priced = [i["price"] for i in items if i.get("price")]
    if sub is not None and priced:
        s = round(sum(priced), 2)
        if abs(s - sub) <= max(1.0, 0.01 * sub):
            checks.append(check("items_sum", "pass", "items", f"Line items add up to the subtotal {inr(sub)}."))
        else:
            checks.append(check("items_sum", "warn", "items",
                                f"Line items add up to {inr(s)}, the subtotal says {inr(sub)} - "
                                "some rows may be missing or misread."))
    return fields, checks
