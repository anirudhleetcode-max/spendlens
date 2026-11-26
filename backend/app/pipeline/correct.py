"""Stage 2b - repair common OCR mistakes before extraction.

Tesseract's typical errors on receipts are character confusions, not missing lines:
  numbers   `1,2O4.5O` (O for 0), `l2.50` (l for 1), `4S.00` (S for 5), `12 . 50` (spaces), `12.5O`
  keywords  `T0TAL`, `TOTA1`, `GRAND T0TAL`, `DA7E`, `SUBT0TAL`, `CGS7` - the extractor's regexes miss these
Each repair is small, local and logged, so the review screen and the error analysis can show what was
changed. Nothing here invents digits: a token is only rewritten when it is already mostly digits (numbers)
or within one confusable edit of a known receipt keyword.

`correct_lines()` returns new OcrLine objects (words and confidences kept) plus a list of
{"line", "from", "to", "kind"} corrections.
"""
from __future__ import annotations

import re
from dataclasses import replace

# letters Tesseract reads in place of digits on thermal print
TO_DIGIT = {"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1", "i": "1", "!": "1",
            "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "g": "9", "q": "9", "T": "7"}
# digits read in place of letters inside words
TO_LETTER = {"0": "O", "1": "L", "5": "S", "8": "B", "2": "Z", "6": "G", "7": "T", "4": "A", "3": "E"}

KEYWORDS = ["TOTAL", "SUBTOTAL", "GRAND", "AMOUNT", "PAYABLE", "NET", "BALANCE", "CHANGE", "CASH",
            "DATE", "INVOICE", "RECEIPT", "ROUNDING", "ROUND", "DISCOUNT", "CGST", "SGST", "IGST", "GST",
            "TAX", "QTY", "RATE", "PRICE", "BILL", "TENDERED", "INCLUSIVE", "INCL", "CARD", "VISA", "UPI"]
_KW = {k for k in KEYWORDS}
# one-letter look-alike edits are only allowed towards these (long, distinctive) words; GRAND, CHANGE etc.
# collide with real names ("Grano", "Chance")
FUZZY_KEYWORDS = ["TOTAL", "SUBTOTAL", "AMOUNT", "PAYABLE", "ROUNDING", "INVOICE", "DISCOUNT", "BALANCE",
                  "TENDERED", "INCLUSIVE"]

# token that is a number with a few letter confusions: starts/ends with digit-ish, mostly digits
_NUMLIKE = re.compile(r"^[\dOoDQlI|iSsBZzGgq!T.,/]+$")
_DIGITISH = set("0123456789")


def _fix_number(tok: str) -> str | None:
    """`1,2O4.5O` -> `1,204.50`. Only when >= 60% of the characters (ignoring separators) are already
    digits, there are at least 2 digits, and the result looks like an amount, date or plain integer."""
    core = tok.strip(".,:")
    if not core or not _NUMLIKE.match(core):
        return None
    chars = [c for c in core if c not in ".,/"]
    digits = sum(c in _DIGITISH for c in chars)
    if digits < 2 or digits == len(chars):
        return None
    fixed = "".join(TO_DIGIT.get(c, c) for c in core)
    amount_or_date = re.fullmatch(r"\d[\d,]*[.,]\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}", fixed)
    # an amount/date shape is strong evidence on its own (`45.OO`); a bare integer needs mostly digits
    if digits / len(chars) < (0.5 if amount_or_date else 0.6):
        return None
    if not amount_or_date:
        # plain integer: only interior letters (`1O0`), never a trailing unit (`500g`, `2S`) or leading word
        if not re.fullmatch(r"\d[\d,]*", fixed) or not (core[0] in _DIGITISH and core[-1] in _DIGITISH):
            return None
    return tok.replace(core, fixed)


def _letters(tok: str) -> str:
    return "".join(TO_LETTER.get(c, c) for c in tok.upper())


def _fix_keyword(tok: str) -> str | None:
    """`T0TAL` -> `TOTAL`, `TOTA1` -> `TOTAL`, `TOTAI` -> `TOTAL`, `5UBTOTAL` -> `SUBTOTAL`.
    Exact match after mapping digits to look-alike letters, or (for keywords of 5+ letters) one edit away
    where the differing character is a known confusion (I/L, U/V, E/F ...)."""
    m = re.match(r"^([^\w]*)([\w|!]+?)([:.\-]*)$", tok)
    if not m:
        return None
    pre, word, post = m.groups()
    if len(word) < 3 or word.upper() in _KW or word.isdigit():
        return None
    if not any(c.isalpha() for c in word):
        return None
    cand = _letters(word)
    if cand in _KW and cand != word.upper():
        return pre + _case_like(word, cand) + post
    if len(word) >= 5:
        for kw in FUZZY_KEYWORDS:
            if len(kw) == len(cand) and kw != cand:
                diff = [(a, b) for a, b in zip(cand, kw) if a != b]
                if len(diff) == 1 and diff[0] in _LOOKALIKE:
                    return pre + _case_like(word, kw) + post
    return None


_LOOKALIKE = {("I", "L"), ("L", "I"), ("V", "U"), ("U", "V"), ("F", "E"), ("E", "F"), ("H", "N"), ("N", "H"),
              ("C", "G"), ("G", "C"), ("R", "A"), ("P", "R"), ("M", "N"), ("N", "M"), ("D", "O"), ("O", "D"),
              ("Q", "O"), ("J", "I"), ("Y", "T")}


def _case_like(src: str, kw: str) -> str:
    if src[:1].isupper() and src[1:].islower():
        return kw.capitalize()
    return kw if sum(c.isupper() for c in src) >= sum(c.islower() for c in src) else kw.lower()


_SPACED_DECIMAL = re.compile(r"(?<=\d) ?([.,]) (?=\d{2}\b)|(?<=\d) ([.,]) ?(?=\d{2}\b)")


def correct_text(text: str) -> tuple[str, list[dict]]:
    changes: list[dict] = []
    new = _SPACED_DECIMAL.sub(lambda m: m.group(1) or m.group(2), text)
    if new != text:
        changes.append({"from": text, "to": new, "kind": "spacing"})
    out = []
    for tok in new.split(" "):
        fixed = _fix_number(tok)
        kind = "number"
        if fixed is None:
            fixed, kind = _fix_keyword(tok), "keyword"
        if fixed is not None and fixed != tok:
            changes.append({"from": tok, "to": fixed, "kind": kind})
            out.append(fixed)
        else:
            out.append(tok)
    return " ".join(out), changes


def correct_lines(lines) -> tuple[list, list[dict]]:
    """Corrected copies of the OCR lines (same objects' type, words untouched) and a change log."""
    out, log = [], []
    for i, ln in enumerate(lines):
        text, changes = correct_text(ln.text)
        for c in changes:
            log.append({"line": i, **c})
        out.append(replace(ln, text=text) if text != ln.text else ln)
    return out, log
