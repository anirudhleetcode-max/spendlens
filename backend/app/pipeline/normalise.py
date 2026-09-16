"""Stage 3 - text normalisation: turn OCR strings into typed values.

Amounts: `1,234.50`, `1,23,456.00` (Indian grouping), `473,00` (OCR comma for a decimal point),
`Rs .497.00`, `₹ 99`, `16, 409.00` (OCR space inside a number), `1,2O4.00` (letter O for zero).
Dates: day-first Indian formats; impossible dates and dates in the future are rejected.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from ..utils import merchant_key  # noqa: F401  (re-exported: normalised merchant key)

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTHS["sept"] = 9

AMOUNT_RE = re.compile(r"(?<![\w.])(?:rs\.?|inr|₹)?\s*\.?\s*(\d{1,3}(?:, ?\d{2,3})+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)"
                       r"(?![\d%]|[.,]\d)", re.I)


def parse_amount(tok: str) -> float | None:
    tok = tok.strip().replace(" ", "")
    m = re.fullmatch(r"(\d[\d,]*)[.,](\d{2})", tok)
    if m:
        whole = m.group(1).replace(",", "")
        return float(f"{whole}.{m.group(2)}") if whole.isdigit() else None
    digits = tok.replace(",", "")
    return float(digits) if digits.isdigit() else None


def fix_ocr_digits(line: str) -> str:
    """O -> 0 and l/I -> 1 when they sit inside a number."""
    fixed = re.sub(r"(?<=\d)[oO](?=[\d.,])|(?<=[\d.,])[oO](?=\d|\b)", "0", line)
    return re.sub(r"(?<=\d)[lI](?=\d)", "1", fixed)


def amounts_in(line: str) -> list[float]:
    out = []
    for m in AMOUNT_RE.finditer(fix_ocr_digits(line)):
        v = parse_amount(m.group(1))
        if v is not None:
            out.append(v)
    return out


def decimal_amounts(line: str) -> list[float]:
    """Only amounts written with paise (x.xx) - far less likely to be a qty, phone or bill number."""
    return [v for v, raw in ((parse_amount(m.group(1)), m.group(1)) for m in AMOUNT_RE.finditer(line))
            if v is not None and re.search(r"[.,]\d{2}$", raw)]


DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4}|\d{2})\b"), "dmy"),        # 16/09/2026
    (re.compile(r"\b(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\b"), "ymd"),             # 2026-09-16
    (re.compile(r"\b(\d{1,2})\s*[\-/ .]?\s*([a-z]{3,9})\.?\s*[\-/ ,.]?\s*(\d{4}|\d{2})\b", re.I), "dMy"),  # 16-Sep-26
    (re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I), "Mdy"),                 # Sep 16, 2026
]


def _mk_date(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    if dt.year < 2000 or dt > date.today() + timedelta(days=2):
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


def nice_name(name: str) -> str:
    name = name.strip(" .-=:|")
    return " ".join(w.capitalize() if w.isalpha() else w.upper() for w in name.split())


def inr(v: float) -> str:
    """₹1,23,456.00 - Indian digit grouping, used in validation messages."""
    neg = v < 0
    whole, frac = f"{abs(v):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{'-' if neg else ''}₹{whole}.{frac}"
