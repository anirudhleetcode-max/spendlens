"""Stage 6 - field-level confidence. Every number the review screen shows comes from here.

    confidence = rule_strength x ocr_quality_term  [x position term]      (from extraction)
                 then adjusted by validation:                              (from validate.py)
                   receipt arithmetic agrees      -> max(conf, 0.95)
                   total repaired by digit swap   -> 0.70  (still flagged)
                   arithmetic disagrees           -> min(conf, 0.60)  (flagged)

`q` is Tesseract's mean word confidence for the line the value came from, divided by 100.
The constants are hand-set, not learned: they order the evidence sensibly (a labelled "Date:" line
beats a stray date; "Grand Total" beats "Total"), and REVIEW_THRESHOLD is where the UI starts asking
the user to check a field. They are *scores*, not calibrated probabilities - see README "Confidence".
"""
from __future__ import annotations

REVIEW_THRESHOLD = 0.6          # fields below this are flagged in the UI

MERCHANT_GUESS = 0.55           # first name-like header line, merchant not in the lexicon
TOTAL_FALLBACK = 0.35           # no total keyword found: largest amount with paise
TAX_NONE = 0.30                 # no tax line found: 0.00 assumed
PAYMENT_FOUND = 0.85
PAYMENT_NONE = 0.20
DATE_LABELLED = 0.95            # line mentions Date / Dt
DATE_UNLABELLED = 0.75
ARITH_AGREES_FLOOR = 0.95
ARITH_REPAIRED = 0.70
ARITH_DISAGREES_CAP = 0.60


def clip(v: float) -> float:
    return max(0.0, min(1.0, v))


def merchant_known(similarity: float, q: float) -> float:
    """Fuzzy lexicon match (similarity >= 0.82) on a header line."""
    return min(1.0, similarity * (0.6 + 0.4 * q))


def merchant_guess(q: float) -> float:
    return MERCHANT_GUESS * q


def date_conf(labelled: bool, q: float) -> float:
    return (DATE_LABELLED if labelled else DATE_UNLABELLED) * (0.5 + 0.5 * q)


def total_keyword(strength: float, q: float, position: float) -> float:
    """strength: keyword rank (1.0 grand total ... 0.6 amount); position 0 (top) .. 1 (bottom)."""
    return strength * (0.55 + 0.4 * q) * (0.9 + 0.1 * position)


def tax_components(mean_q: float) -> float:
    return 0.9 * mean_q


def tax_single(q: float) -> float:
    return 0.6 * q


def item(consistent: bool, q: float) -> float:
    """Line item: qty x rate == amount makes the row trustworthy."""
    return round((0.9 if consistent else 0.6) * q, 2)


def item_loose(q: float) -> float:
    return round(0.6 * q, 2)
