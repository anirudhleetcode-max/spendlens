# Receipt reading: real vs synthetic, and what goes wrong

Numbers from `results/*/metrics.json` and `errors_breakdown.json` (runs dated 2026-09-16,
Tesseract 5.3.4). Exact match unless stated.

## Headline

| test set | receipts | merchant | date | total | OCR CER |
|---|---|---|---|---|---|
| Synthetic Indian bills, held-out seed (`synthetic_test`) — **synthetic** | 60 | 100% | 100% | 96.7% | not measured (no text labels) |
| SROIE test subset, parser 1.1, blind (`sroie_main`) — **real, Malaysia** | 200 | 23.5% | 78.5% | 48.5% | 0.197 |
| SROIE train split as dev set, parser 1.2 (`sroie_dev_parser`) — **real** | 150 | 26.0% | 78.7% | 68.7% | 0.189 |
| CORD test (`cord_main-r2`) — **real, Indonesia** | 100 (95 with a total) | not labelled | not labelled | 24.2% | 0.534 |

The synthetic numbers mostly show the parser agrees with the generator it was built alongside. The real
numbers are the ones to quote. Dates transfer well because SROIE uses day-first dates like India.
Merchants don't, because the parser assumes the first name-like header line is the shop.

## Ablation (SROIE, the same 60 receipts, parser 1.1)

| OCR setting | merchant | date | total | CER | s/receipt |
|---|---|---|---|---|---|
| preprocessing, both variants, PSM 6 (production) | 46.7% | 80.0% | 48.3% | **0.173** | 1.61 |
| raw grayscale, PSM 6 | 41.7% | 75.0% | **53.3%** | 0.208 | 0.77 |
| preprocessing, thresholded image only, PSM 6 | 36.7% | 75.0% | 48.3% | 0.199 | 2.01 |
| preprocessing, both, PSM 4 | 41.7% | 75.0% | **53.3%** | 0.210 | 1.89 |
| preprocessing, both, PSM 11 | 43.3% | **81.7%** | 48.3% | 0.314 | 1.96 |
| raw grayscale, PSM 4 | 43.3% | 68.3% | 51.7% | 0.214 | 0.78 |

On CORD (photos, not scans) preprocessing matters much more: CER 0.534 with it vs 0.926 without
(50 receipts), total 24.2% vs 19.1%.

Reading:
- SROIE images are flat, clean scans. Paper detection and deskewing add little, and reading both
  image variants mainly helps the header (merchant, date). With 60 receipts, a 5-point difference in
  totals is three receipts, which is within noise. I kept the production setting because it gives the
  lowest CER on both real sets and is much better on photos, which is what users upload.
- Reading two variants and keeping the more confident one beats the thresholded image alone on every
  field.
- PSM 11 ("sparse text") breaks line structure (CER 0.314), which the line-based rules depend on.

## Error analysis (SROIE test, parser 1.1, 276 field errors)

From `results/sroie_main-20260916/errors_breakdown.json` and reading `errors.md`:

**Total (103 errors)**
- 45 fell back to "largest amount". Reading them showed 32 had a total line like `TOTAL (GST INCL)` or
  `Total Sales Inclusive GST @6%`, which the rule excluding GST lines threw away. Indian bills print
  "Total (incl. GST)" too, so this was a real bug. **Fix → parser 1.2.** Checked on the SROIE *train*
  split, which the fix was not designed on: 56.0% → 68.7%. Re-scoring the test subset gives 57.5%, but
  that number is post-hoc.
- 34 picked the wrong total-like line: `Total 0% supplies: 22.33`, `GST payable (6%): 0.39`,
  `Total Qty` variants the exclusions don't cover.
- 16 are OCR digit errors on the right line (`8.24` for `4.30`, `1.82` for `1.52`). Arithmetic
  repair only works when a subtotal line was read correctly.
- 44 wrong totals still had confidence ≥ 0.6, so the UI would not flag them. In some the arithmetic
  check raised confidence when it shouldn't have. For example, `X51006311714` has a fallback total of
  22.49 with confidence 0.95, because `SUBTOTAL 22.44` plus the rounding line happened to agree. The
  check trusts the subtotal too readily.

**Merchant (130 errors)**
- 92 are the wrong header line: SROIE receipts often start with a person's name ("TAN CHAY YEE"),
  "COPY", "POSTED" or logo noise. The rule "first name-like line" is Indian-bill specific and fails
  here.
- 22 had no name-like line in the first six (names with registration numbers such as
  `GARDENIA BAKERIES (KL) SDN BHD (139386 X)` fail the letters-only test).
- 14 read the right line but OCR garbled it (`GARDENLA BAKERIES (KL) SON BIED`).
- Only 2 were false matches against the Indian lexicon (`Cred`).

**Date (43 errors)**
- 24 found no date (OCR broke the digits, or formats like `19Mar 2018` without a space before the year).
- 14 were one misread digit (`2015` for `2018`, `26/03` for `25/03`). A few look like label noise: the
  printed date differs from the label.
- 5 picked another date on the receipt (card expiry `31/08/20`, print time vs closing time).

**CORD (72 total errors)**
- 44 found no total at all, and 8 had the right digits in the wrong format. Indonesian receipts write
  `40.000` (forty thousand) and OCR splits `40 ,000`. The amount rules expect `40,000.00`, so this is
  mostly a locale gap, not an OCR one.

## What this suggests next

1. Merchant: learn a line classifier over header lines (position, casing, suffixes like
   "SDN BHD" / "PVT LTD" / "LLP", presence of a registration number) instead of taking the first name-like line.
2. Totals: rank candidates by agreement with payment lines (`CASH`, `VISA`, `Total Paid`), not only by keyword.
3. Make the arithmetic check stricter: only raise confidence when both sides were read with high OCR confidence.
4. Locale-aware amount parsing, if non-Indian receipts matter.
5. Collect a small labelled set of real Indian bills. Without it, the Indian-specific rules are only tested on synthetic data.
