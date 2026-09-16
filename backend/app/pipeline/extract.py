"""Stage 4 - field extraction: OCR lines -> candidate values with evidence.

Rules, in plain words:
- merchant: fuzzy-match the first header lines against the known-merchant lexicon; otherwise the first
  header line that looks like a name (mostly letters, not an address / GSTIN / phone / "TAX INVOICE").
- date: day-first Indian formats; a line mentioning "date"/"dt" wins over a stray date.
- total: lines with a total-like keyword, ranked (grand total > net amount/payable > bill amount >
  total amount > total > amount); subtotal / tax / qty / savings lines are excluded; the last amount on
  the line is used. Fallback: the largest amount with paise on the receipt (low confidence).
- tax: CGST + SGST (+ IGST / UTGST / cess / VAT) amounts, else a "GST"/"tax" line.
- payment mode: keywords (UPI, GPay, PhonePe, card networks, cash, wallet).
- items: "name qty rate amount" / "name qty amount" / "name amount" rows above the totals block.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

from . import confidence as C
from .lexicon import known_merchants
from .normalise import amounts_in, decimal_amounts, find_dates, merchant_key, nice_name, parse_amount

TOTAL_KEYS = [  # (regex, strength)
    (r"grand\s*-?\s*tota[l1i]", 1.0),
    (r"net\s*(amount|amt|payable|total|bill)", 0.95),
    (r"(amount|amt)\s*payable|total\s*payable|to\s*pay|payable", 0.93),
    (r"bill\s*(amount|amt|total)", 0.9),
    (r"total\s*(amount|amt|rs|inr|₹)", 0.88),
    (r"sale\s*amount|invoice\s*(amount|total|value)", 0.85),
    (r"\btota[l1i]\b", 0.75),
    (r"^\s*(amount|amt)\b", 0.6),
]
NOT_TOTAL = re.compile(r"sub\s*-?\s*tota|total\s*(qty|quantity|items?|tax|gst|savings?|discount|disc)|"
                       r"\bqty\b|saved|saving|discount|round\s*off|cgst|sgst|igst|\bgst\b|\btax\b|"
                       r"tendered|change|balance|cashback|mrp|rate\s*/?\s*l", re.I)
SKIP_ITEM = re.compile(r"total|tax|gst|cgst|sgst|igst|cess|round|amount|payment|cash|card|upi|change|"
                       r"bill\s*no|date|time|cashier|table|covers|gstin|invoice|thank|saved|discount|"
                       r"^item|qty|rate|mrp|balance|tender|phone|ph:|vehicle|nozzle", re.I)
HEADER_NOISE = re.compile(r"gstin|gst\s*no|tax\s*invoice|^bill\b|invoice|ph[:.]|phone|tel|mob|www|@|"
                          r"\bfssai\b|\bcin\b|\d{6}|road|street|nagar|sector|floor|shop\s*no|near|opp", re.I)


@dataclass
class Field:
    value: object
    confidence: float
    source: str = ""        # how it was found: "lexicon", "header", "keyword:grand total", "fallback", ...
    line: int | None = None  # index of the OCR line it came from (for the preview)

    def as_dict(self):
        d = {"value": self.value, "confidence": round(C.clip(self.confidence), 2), "source": self.source}
        if self.line is not None:
            d["line"] = self.line
        return d


def q(line) -> float:
    return line.conf / 100


# ---------- merchant ----------

@lru_cache
def _known() -> list[tuple[str, str]]:
    return [(merchant_key(m), m) for m in known_merchants()]


def match_known_merchant(text: str) -> tuple[str, float] | None:
    key = merchant_key(text)
    if len(key) < 3:
        return None
    compact = key.replace(" ", "")
    best, best_score = None, 0.0
    for k, name in _known():
        kc = k.replace(" ", "")
        if len(kc) < 3:
            continue
        score = SequenceMatcher(None, compact, kc).ratio()
        if kc == compact:
            score = 1.0
        elif len(kc) >= 5 and kc in compact and len(compact) <= len(kc) + 6:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = name, score
    return (best, best_score) if best and best_score >= 0.82 else None


def _looks_like_name(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    return letters >= 3 and letters / max(1, len(text.replace(" ", ""))) > 0.7 and not HEADER_NOISE.search(text)


def extract_merchant(lines) -> Field:
    for i, ln in enumerate(lines[:4]):
        hit = match_known_merchant(ln.text)
        if hit:
            return Field(hit[0], C.merchant_known(hit[1], q(ln)), "lexicon", i)
    for i, ln in enumerate(lines[:6]):
        if _looks_like_name(ln.text):
            name = re.sub(r"[^\w&'.\- ]", "", ln.text).strip()
            name = " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in name.split())
            return Field(name, C.merchant_guess(q(ln)), "header", i)
    return Field("", 0.0, "none")


# ---------- date ----------

def extract_date(lines) -> Field:
    best: Field | None = None
    for i, ln in enumerate(lines):
        found = find_dates(ln.text)
        if not found:
            continue
        labelled = bool(re.search(r"\b(date|dt|dated|[o0]t)\b", ln.text, re.I))
        score = C.date_conf(labelled, q(ln))
        if best is None or score > best.confidence:
            best = Field(found[0].isoformat(), score, "labelled" if labelled else "unlabelled", i)
    return best or Field(None, 0.0, "none")


# ---------- totals / tax ----------

# "Total (incl. GST)", "Total Sales Inclusive GST @6%", "Total with GST": the payable total, even though
# the line mentions GST. Added in parser 1.2 after error analysis (see README "Error analysis").
TAX_INCLUSIVE_TOTAL = re.compile(
    r"tota\w*\b.{0,25}\b(incl\w*|inclusive|includes|with)\b.{0,6}(gst|tax|vat)"   # Total incl. GST
    r"|tota\w*\b.{0,12}\b(gst|tax|vat)\s*(incl\w*|inclusive)", re.I)                # TOTAL (GST INCL)


def extract_total(lines, tax_inclusive_rule: bool = True) -> Field:
    candidates: list[Field] = []
    n = len(lines)
    for i, ln in enumerate(lines):
        text = ln.text
        keep = re.search(r"grand|net\s*(amount|payable)|bill\s*amount", text, re.I) or (
            tax_inclusive_rule and TAX_INCLUSIVE_TOTAL.search(text) and not re.search(r"sub\s*-?\s*tota", text, re.I))
        if NOT_TOTAL.search(text) and not keep:
            continue
        for rx, strength in TOTAL_KEYS:
            m = re.search(rx, text, re.I)
            if m:
                vals = amounts_in(re.split(rx, text, maxsplit=1, flags=re.I)[-1]) or amounts_in(text)
                vals = [v for v in vals if 0 < v < 1e7]
                src_line = i
                if not vals and i + 1 < n:  # amount wrapped onto the next line
                    vals = [v for v in decimal_amounts(lines[i + 1].text) if 0 < v < 1e7]
                    src_line = i + 1
                if vals:
                    position = i / max(1, n - 1)  # totals live in the lower half
                    candidates.append(Field(round(vals[-1], 2), C.total_keyword(strength, q(ln), position),
                                            f"keyword:{m.group(0).lower().strip()}", src_line))
                break
    if candidates:
        return max(candidates, key=lambda f: f.confidence)
    best: Field | None = None
    for i, ln in enumerate(lines):
        if re.search(r"gstin|ph[:.]|phone|mob|vehicle|bill\s*no|invoice\s*no|card|xxxx|saved", ln.text, re.I):
            continue
        for v in decimal_amounts(ln.text):
            if 0 < v < 1e6 and (best is None or v > best.value):
                best = Field(round(v, 2), C.TOTAL_FALLBACK, "fallback:largest amount", i)
    return best or Field(None, 0.0, "none")


def extract_tax(lines) -> Field:
    parts, confs, first = [], [], None
    for i, ln in enumerate(lines):
        t = ln.text
        if re.search(r"gstin|gst\s*no", t, re.I):
            continue
        if re.search(r"\b(c|s|i|ut)\s*gst\b|\bcess\b|\bvat\b", t, re.I):
            vals = decimal_amounts(re.sub(r"@?\s*\d+(\.\d+)?\s*%", " ", t))
            if vals:
                parts.append(vals[-1]); confs.append(q(ln))
                first = i if first is None else first
    if parts:
        return Field(round(sum(parts), 2), C.tax_components(sum(confs) / len(confs)),
                     f"components:{len(parts)}", first)
    for i, ln in enumerate(lines):
        if re.search(r"(total\s*)?(gst|tax)\b(?!\s*in)", ln.text, re.I) and not re.search(r"gstin|invoice", ln.text, re.I):
            vals = decimal_amounts(re.sub(r"@?\s*\d+(\.\d+)?\s*%", " ", ln.text))
            if vals:
                return Field(round(vals[-1], 2), C.tax_single(q(ln)), "tax line", i)
    return Field(0.0, C.TAX_NONE, "none")


PAYMENT_RULES = [
    ("UPI", r"\bupi\b|g\s*pay|google\s*pay|phone\s*pe|bhim|@ok|@ybl|@paytm"),
    ("Wallet", r"paytm\s*wallet|wallet|amazon\s*pay|mobikwik"),
    ("Card", r"\bcard\b|visa|master\s*card|rupay|debit|credit|amex|xxxx|\*{4}"),
    ("Net Banking", r"net\s*banking|neft|imps"),
    ("Cash", r"\bcash\b"),
]


def extract_payment(lines) -> Field:
    for mode, rx in PAYMENT_RULES:
        for i, ln in enumerate(lines):
            if re.search(rx, ln.text, re.I):
                return Field(mode, C.PAYMENT_FOUND, "keyword", i)
    return Field("Unknown", C.PAYMENT_NONE, "none")


# ---------- items ----------

ITEM_FULL = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9 &'()./+\-]{1,40}?)\s+[=:|]?\s*(?P<qty>\d{1,3}(?:\.\d{1,3})?)[)\]|]?"
                       r"(?:\s+|\s*[x×*]\s*)[=:|]?\s*(?P<rate>\d[\d,]*[.,]\d{2})\s+[=:|]?\s*(?P<amt>\d[\d,]*[.,]\d{2})\s*$")
ITEM_QTY_AMT = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9 &'()./+\-]{1,40}?)\s+(?P<qty>\d{1,2})\s+(?P<amt>\d[\d,]*[.,]\d{2})\s*$")
ITEM_AMT = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9 &'()./+\-]{2,40}?)\s+[=:|]?\s*(?:rs\.?\s*)?(?P<amt>\d[\d,]*[.,]\d{2})\s*$", re.I)


def _fuel_item(lines) -> list[dict]:
    text = "\n".join(l.text for l in lines)
    prod = re.search(r"product\s*[:\-]?\s*([A-Za-z][A-Za-z ]{2,20})", text, re.I)
    vol = re.search(r"\b(volume|vol|qty|litres?)\b\s*(\(l\))?\s*[:\-]?\s*(\d+[.,]\d{1,3})", text, re.I)
    if prod and vol:
        return [{"name": nice_name(prod.group(1)), "qty": float(vol.group(3).replace(",", ".")), "price": None,
                 "confidence": 0.6}]
    return []


def extract_items(lines) -> list[dict]:
    items = []
    started = False
    for ln in lines:
        t = ln.text.strip()
        if re.search(r"\bitem|description|particulars", t, re.I) and re.search(r"qty|amount|amt|rate|price", t, re.I):
            started = True
            continue
        if re.search(r"sub\s*total|total\s*qty|grand|net\s*amount|^total", t, re.I) and items:
            break
        if SKIP_ITEM.search(t) and not ITEM_FULL.match(t):
            continue
        m = ITEM_FULL.match(t)
        if m:
            qty = float(m.group("qty"))
            amt = parse_amount(m.group("amt"))
            rate = parse_amount(m.group("rate"))
            if amt is None:
                continue
            # sanity: qty*rate should be close to amount; if not, trust amount and rate
            ok = rate is not None and abs(qty * rate - amt) <= max(1.0, 0.02 * amt)
            if not ok and rate and abs(amt / rate - round(amt / rate)) < 0.01 and 0 < round(amt / rate) < 1000:
                qty, ok = float(round(amt / rate)), True
            items.append({"name": nice_name(m.group("name")), "qty": qty, "price": amt,
                          "confidence": C.item(ok, q(ln))})
            started = True
            continue
        if not started:
            continue
        m = ITEM_QTY_AMT.match(t) or ITEM_AMT.match(t)
        if m:
            amt = parse_amount(m.group("amt"))
            if amt is None:
                continue
            qty = float(m.groupdict().get("qty") or 1)
            items.append({"name": nice_name(m.group("name")), "qty": qty, "price": amt,
                          "confidence": C.item_loose(q(ln))})
    return items[:60] or _fuel_item(lines)
