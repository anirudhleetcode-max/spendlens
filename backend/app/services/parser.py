"""OCR lines -> structured expense fields, each with a confidence in [0, 1].

Rules, in plain words:
- merchant: fuzzy-match the first header lines against known Indian merchants; otherwise the first
  line in the header that looks like a name (mostly letters, not an address/GSTIN/phone/"TAX INVOICE").
- date: many Indian formats, day-first; lines mentioning "date"/"dt" win; must be a real date not far
  in the future.
- total: lines with a total-like keyword, ranked (grand total > net amount/payable > bill amount >
  total amount > total > amount); subtotal / tax / qty / savings lines are excluded; the last amount on
  the line is used. Fallback: the largest plausible amount on the receipt (lower confidence).
- tax: CGST + SGST (+ IGST / UTGST / cess) amounts, else a "GST"/"tax" line.
- payment mode: keywords (UPI, GPay, PhonePe, card networks, cash, wallet).
- items: "name qty rate amount" / "name qty amount" / "name amount" rows above the totals block.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from functools import lru_cache

from ..utils import merchant_key

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTHS["sept"] = 9

# amount: 1,234.50 | 1234.50 | 473,00 (OCR comma for dot) | Rs .497.00 | ₹ 99
AMOUNT_RE = re.compile(r"(?<![\w.])(?:rs\.?|inr|₹)?\s*\.?\s*(\d{1,3}(?:, ?\d{2,3})+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)"
                       r"(?![\d%]|[.,]\d)", re.I)

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

    def as_dict(self):
        return {"value": self.value, "confidence": round(max(0.0, min(1.0, self.confidence)), 2)}


def parse_amount(tok: str) -> float | None:
    tok = tok.strip()
    tok = tok.replace(" ", "")
    m = re.fullmatch(r"(\d[\d,]*)[.,](\d{2})", tok)
    if m:
        whole = m.group(1).replace(",", "")
        return float(f"{whole}.{m.group(2)}") if whole.isdigit() else None
    digits = tok.replace(",", "")
    return float(digits) if digits.isdigit() else None


def amounts_in(line: str) -> list[float]:
    # OCR habitually reads O for 0 and l/I for 1 inside numbers
    fixed = re.sub(r"(?<=\d)[oO](?=[\d.,])|(?<=[\d.,])[oO](?=\d|\b)", "0", line)
    fixed = re.sub(r"(?<=\d)[lI](?=\d)", "1", fixed)
    out = []
    for m in AMOUNT_RE.finditer(fixed):
        v = parse_amount(m.group(1))
        if v is not None:
            out.append(v)
    return out


def decimal_amounts(line: str) -> list[float]:
    """Only amounts written with paise (x.xx) - far less likely to be a qty, phone or bill number."""
    return [v for v, raw in ((parse_amount(m.group(1)), m.group(1)) for m in AMOUNT_RE.finditer(line))
            if v is not None and re.search(r"[.,]\d{2}$", raw)]


# ---------- merchant ----------

@lru_cache
def _known() -> list[tuple[str, str]]:
    from ml.dataset import known_merchants
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


def parse_merchant(lines) -> Field:
    header = lines[:6]
    for ln in header[:4]:
        hit = match_known_merchant(ln.text)
        if hit:
            return Field(hit[0], min(1.0, hit[1] * (0.6 + ln.conf / 250)))
    for ln in header:
        if _looks_like_name(ln.text):
            name = re.sub(r"[^\w&'.\- ]", "", ln.text).strip()
            name = " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in name.split())
            return Field(name, 0.55 * ln.conf / 100)
    return Field("", 0.0)


# ---------- date ----------

DATE_PATTERNS = [
    # 16/09/2026, 16-09-26, 16.09.2026
    (re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4}|\d{2})\b"), "dmy"),
    # 2026-09-16
    (re.compile(r"\b(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\b"), "ymd"),
    # 16-Sep-2026, 16 Sep 26, 16 September 2026
    (re.compile(r"\b(\d{1,2})\s*[\-/ .]?\s*([a-z]{3,9})\.?\s*[\-/ ,.]?\s*(\d{4}|\d{2})\b", re.I), "dMy"),
    # Sep 16, 2026
    (re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I), "Mdy"),
]


def _mk_date(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    today = date.today()
    if dt.year < 2000 or dt > today + timedelta(days=2):
        return None
    return dt


def _month_num(tok: str) -> int | None:
    tok = tok.lower()
    return MONTHS.get(tok[:4] if tok[:4] == "sept" else tok[:3])


def find_dates(text: str) -> list[date]:
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            a, b, c = m.groups()
            if kind == "dmy":
                dt = _mk_date(int(c), int(b), int(a))
                if dt is None and int(b) > 12:  # US-style fallback 09/16/2026
                    dt = _mk_date(int(c), int(a), int(b))
            elif kind == "ymd":
                dt = _mk_date(int(a), int(b), int(c))
            elif kind == "dMy":
                mm = _month_num(b)
                dt = _mk_date(int(c), mm, int(a)) if mm else None
            else:
                mm = _month_num(a)
                dt = _mk_date(int(c), mm, int(b)) if mm else None
            if dt:
                out.append(dt)
    return out


def parse_date(lines) -> Field:
    best: tuple[float, date] | None = None
    for ln in lines:
        found = find_dates(ln.text)
        if not found:
            continue
        labelled = bool(re.search(r"\b(date|dt|dated|[o0]t)\b", ln.text, re.I))
        score = (0.95 if labelled else 0.75) * (0.5 + ln.conf / 200)
        if best is None or score > best[0]:
            best = (score, found[0])
    if best:
        return Field(best[1].isoformat(), best[0])
    return Field(None, 0.0)


# ---------- totals / tax ----------

def parse_total(lines) -> Field:
    candidates = []
    n = len(lines)
    for i, ln in enumerate(lines):
        text = ln.text
        if NOT_TOTAL.search(text) and not re.search(r"grand|net\s*(amount|payable)|bill\s*amount", text, re.I):
            continue
        for rx, strength in TOTAL_KEYS:
            if re.search(rx, text, re.I):
                vals = amounts_in(re.split(rx, text, maxsplit=1, flags=re.I)[-1]) or amounts_in(text)
                vals = [v for v in vals if 0 < v < 1e7]
                if not vals and i + 1 < n:  # amount wrapped onto the next line
                    vals = [v for v in decimal_amounts(lines[i + 1].text) if 0 < v < 1e7]
                if vals:
                    position = i / max(1, n - 1)  # totals live in the lower half
                    score = strength * (0.55 + ln.conf / 250) * (0.9 + 0.1 * position)
                    candidates.append((score, vals[-1]))
                break
    if candidates:
        score, val = max(candidates, key=lambda c: c[0])
        return Field(round(val, 2), score)
    # fallback: biggest amount with paise that is not on an obviously-wrong line
    pool = []
    for ln in lines:
        if re.search(r"gstin|ph[:.]|phone|mob|vehicle|bill\s*no|invoice\s*no|card|xxxx|saved", ln.text, re.I):
            continue
        pool += [v for v in decimal_amounts(ln.text) if 0 < v < 1e6]
    if pool:
        return Field(round(max(pool), 2), 0.35)
    return Field(None, 0.0)


def parse_tax(lines) -> Field:
    parts, confs = [], []
    for ln in lines:
        t = ln.text
        if re.search(r"gstin|gst\s*no", t, re.I):
            continue
        if re.search(r"\b(c|s|i|ut)\s*gst\b|\bcess\b|\bvat\b", t, re.I):
            vals = decimal_amounts(re.sub(r"@?\s*\d+(\.\d+)?\s*%", " ", t))
            if vals:
                parts.append(vals[-1]); confs.append(ln.conf)
    if parts:
        return Field(round(sum(parts), 2), 0.9 * (sum(confs) / len(confs)) / 100)
    for ln in lines:
        if re.search(r"(total\s*)?(gst|tax)\b(?!\s*in)", ln.text, re.I) and not re.search(r"gstin|invoice", ln.text, re.I):
            vals = decimal_amounts(re.sub(r"@?\s*\d+(\.\d+)?\s*%", " ", ln.text))
            if vals:
                return Field(round(vals[-1], 2), 0.6 * ln.conf / 100)
    return Field(0.0, 0.3)


PAYMENT_RULES = [
    ("UPI", r"\bupi\b|g\s*pay|google\s*pay|phone\s*pe|bhim|@ok|@ybl|@paytm"),
    ("Wallet", r"paytm\s*wallet|wallet|amazon\s*pay|mobikwik"),
    ("Card", r"\bcard\b|visa|master\s*card|rupay|debit|credit|amex|xxxx|\*{4}"),
    ("Net Banking", r"net\s*banking|neft|imps"),
    ("Cash", r"\bcash\b"),
]


def parse_payment(lines) -> Field:
    text = "\n".join(l.text for l in lines)
    for mode, rx in PAYMENT_RULES:
        if re.search(rx, text, re.I):
            return Field(mode, 0.85)
    return Field("Unknown", 0.2)


# ---------- items ----------

ITEM_FULL = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9 &'()./+\-]{1,40}?)\s+[=:|]?\s*(?P<qty>\d{1,3}(?:\.\d{1,3})?)[)\]|]?"
                       r"(?:\s+|\s*[x×*]\s*)[=:|]?\s*(?P<rate>\d[\d,]*[.,]\d{2})\s+[=:|]?\s*(?P<amt>\d[\d,]*[.,]\d{2})\s*$")
ITEM_QTY_AMT = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9 &'()./+\-]{1,40}?)\s+(?P<qty>\d{1,2})\s+(?P<amt>\d[\d,]*[.,]\d{2})\s*$")
ITEM_AMT = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9 &'()./+\-]{2,40}?)\s+[=:|]?\s*(?:rs\.?\s*)?(?P<amt>\d[\d,]*[.,]\d{2})\s*$", re.I)


def _nice(name: str) -> str:
    name = name.strip(" .-=:|")
    return " ".join(w.capitalize() if w.isalpha() else w.upper() for w in name.split())


def _fuel_item(lines) -> list[dict]:
    text = "\n".join(l.text for l in lines)
    prod = re.search(r"product\s*[:\-]?\s*([A-Za-z][A-Za-z ]{2,20})", text, re.I)
    vol = re.search(r"\b(volume|vol|qty|litres?)\b\s*(\(l\))?\s*[:\-]?\s*(\d+[.,]\d{1,3})", text, re.I)
    if prod and vol:
        return [{"name": _nice(prod.group(1)), "qty": float(vol.group(3).replace(",", ".")), "price": None,
                 "confidence": 0.6}]
    return []


def parse_items(lines) -> list[dict]:
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
            items.append({"name": _nice(m.group("name")), "qty": qty, "price": amt,
                          "confidence": round((0.9 if ok else 0.6) * ln.conf / 100, 2)})
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
            items.append({"name": _nice(m.group("name")), "qty": qty, "price": amt,
                          "confidence": round(0.6 * ln.conf / 100, 2)})
    return items[:60] or _fuel_item(lines)


CONFUSABLE = {"6": "0", "8": "0", "9": "0", "0": "8", "5": "6", "3": "8", "1": "7", "7": "1"}


def _digit_variants(value: float) -> set[float]:
    """Totals with one or two commonly-confused digits swapped (thermal print 0 read as 6/8 etc.)."""
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


def expected_total(lines, tax: float) -> float | None:
    """What the receipt's own arithmetic says the total should be (subtotal + tax, or rate x volume)."""
    for ln in lines:
        if re.search(r"sub\s*-?\s*tota", ln.text, re.I):
            vals = decimal_amounts(ln.text)
            if vals:
                return vals[-1] + (tax or 0) + round_off(lines)
    text = "\n".join(l.text for l in lines)
    rate = re.search(r"rate\s*/?\s*l\w*\s*[:\-]?\s*(\d+[.,]\d{2})", text, re.I)
    vol = re.search(r"(volume|vol)\s*(\(l\))?\s*[:\-]?\s*(\d+[.,]\d{1,3})", text, re.I)
    if rate and vol:
        return float(rate.group(1).replace(",", ".")) * float(vol.group(3).replace(",", "."))
    return None


def round_off(lines) -> float:
    for ln in lines:
        if re.search(r"round\s*-?\s*off|rounding", ln.text, re.I):
            m = re.search(r"([+-]?)\s*(\d+)[.,](\d{2})\s*$", ln.text)
            if m:
                v = float(f"{m.group(2)}.{m.group(3)}")
                return -v if m.group(1) == "-" else v
    return 0.0


def reconcile_total(total: Field, lines, tax: float) -> Field:
    """Check the total against the receipt's own arithmetic. If it is off, try the total with commonly
    confused digits swapped and keep the variant that makes the bill add up."""
    exp = expected_total(lines, tax)
    if total.value is None or exp is None:
        return total
    # with a round-off line the sum should be exact; without one it is within a rupee
    has_ro = round_off(lines) != 0
    keep_tol = 0.02 if has_ro else max(1.0, 0.005 * exp)
    repair_tol = 0.15 if has_ro else keep_tol  # a line item or subtotal may itself be off by a digit
    err = abs(total.value - exp)
    if err <= keep_tol:
        total.confidence = max(total.confidence, 0.95)
        return total
    best_err, best = min((abs(v - exp), v) for v in _digit_variants(total.value))
    if best_err <= repair_tol and best_err < err:
        return Field(round(best, 2), 0.7)  # repaired: keep it flagged for review
    total.confidence = min(total.confidence, 0.6)  # the numbers don't add up - ask the user
    return total


def parse_receipt(lines) -> dict:
    fields = {
        "merchant": parse_merchant(lines),
        "date": parse_date(lines),
        "total": parse_total(lines),
        "tax": parse_tax(lines),
        "payment_mode": parse_payment(lines),
    }
    fields["total"] = reconcile_total(fields["total"], lines, fields["tax"].value or 0)
    items = parse_items(lines)
    for it in items:
        if it["price"] is None:
            it["price"] = fields["total"].value or 0.0
    return {"fields": {k: v.as_dict() for k, v in fields.items()}, "items": items}


def parsed_date_or_today(value: str | None) -> date:
    try:
        return datetime.fromisoformat(value).date() if value else date.today()
    except ValueError:
        return date.today()
