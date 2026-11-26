# OCR configurations, OCR-error correction and image quality

Measured 2026-11-26 with Tesseract 5.3.4 (LSTM) on a 4-CPU container. All numbers come from
`experiments/results/*/metrics.json`; `python -m experiments.summarise` regenerates the tables in
`summary.md`. Small sets: on 60 receipts one receipt is 1.7 points, so differences under ~5 points
are not evidence of anything.

## 1. Parser 1.3: handling incorrect OCR output

Two changes, both found by reading errors on the **SROIE train split** (used as a development set),
then frozen before the test split was re-run:

- `app/pipeline/correct.py` repairs typical Tesseract confusions before extraction: letters inside
  amounts and dates (`1,2O4.5O`, `4S.00`, `1O/O3/2O18`), spaced decimals (`12 . 50`) and keywords one
  confusable character away (`T0TAL`, `TOTA1`, `CGS7`). It refuses to touch units (`500g`), names one
  letter from a keyword (`Grano`), bill numbers and phone numbers. Each repair is logged and shown on
  the review screen as "Fixed N likely OCR misreads".
- When no total line is readable, the largest-amount fallback no longer considers cash-tendered and
  change lines. The first version of the correction exposed this: repairing `Cash -50. 00` made the
  cash handed over the largest amount on a receipt whose total line read `Total RM Inel. of GST 9.65`.

| set | parser 1.2 | 1.3 without correction | 1.3 |
|---|---|---|---|
| SROIE train / dev, 150 receipts (`sroie_dev_correction`) | 58.4% | 60.4% | **62.4%** |
| SROIE test, 200 receipts, blind (`sroie_main_parser13`) | 57.5% | — | **60.5%** |
| CORD test, 95 with a total (`cord_main_parser13`) | 24.2% | — | 25.3% |
| synthetic held-out, 60 (`synthetic_test_parser13`): GST | 94.0% | — | 96.0% |

Total exact-match accuracy. Merchant and date did not change on any set. On the dev split no receipt
that 1.2 got right became wrong. Corrections fire on about 0.5 lines per SROIE receipt (0.52 dev, 0.43 test).

## 2. Field-level precision / recall (parser 1.3, SROIE test, 200 receipts)

| field | precision | recall | F1 | auto-accepted precision / recall |
|---|---|---|---|---|
| merchant | 26.4% | 23.5% | 0.249 | 0% / 0% (1 receipt auto-accepted, a wrong lexicon match) |
| date | 89.2% | 78.5% | 0.835 | 89.4% / 72.0% |
| total | 62.7% | 60.5% | 0.616 | 70.8% / 54.5% |

Total within 1% of the label: 69.0%. OCR: CER 0.197, WER 0.442. WER is much higher than CER because
one wrong character makes the whole word wrong, and SROIE's labels split tokens differently from
Tesseract (`RM 12.00` vs `RM12.00`). Precision is above recall for every field: when the parser is
wrong it is more often because it found nothing than because it found the wrong thing. The review
threshold trades about 6 points of total recall for 8 points of precision.

## 3. OCR configuration comparison

One change at a time against production. Production = preprocessing (resize, paper crop,
NL-means denoise, deskew, adaptive Gaussian threshold), Tesseract run on both the binary and the
grayscale image keeping the more confident read, PSM 6, LSTM engine. The legacy engine (OEM 0/2)
could not be compared: the installed `eng.traineddata` is LSTM-only.

| setting | SROIE dev (60) total / CER | CORD photos (50) total / CER | synthetic (40) total / CER |
|---|---|---|---|
| **production** | 65.0% / 0.165 | 29.8% / **0.403** | 95.0% / 0.004 |
| no preprocessing (raw grayscale) | 63.3% / 0.188 | 19.2% / 0.926 | 97.5% / 0.010 |
| binary image only | 63.3% / 0.193 | 31.9% / 0.436 | 90.0% / 0.006 |
| grayscale only (no threshold) | 61.7% / 0.163 | 23.4% / 0.528 | 100% / 0.005 |
| threshold: adaptive mean | 65.0% / 0.164 | 31.9% / 0.430 | 97.5% / 0.004 |
| threshold: Otsu (global) | 60.0% / 0.163 | 27.7% / 0.536 | 97.5% / 0.004 |
| threshold: Sauvola | 65.0% / 0.162 | 34.0% / 0.411 | 95.0% / 0.004 |
| denoise: median 3×3 | 51.7% / 0.191 | 27.7% / 0.502 | 97.5% / 0.008 |
| denoise: bilateral | 60.0% / 0.168 | 34.0% / 0.497 | 95.0% / 0.004 |
| denoise: none | 60.0% / 0.174 | 29.8% / 0.573 | 90.0% / 0.007 |
| no deskew | 68.3% / 0.167 | 23.4% / 0.418 | 95.0% / 0.004 |
| PSM 3 (automatic layout) | 58.3% / 0.178 | 17.0% / 0.440 | 20.0% / 0.259 |
| PSM 4 (single column) | 61.7% / 0.191 | 25.5% / 0.460 | 20.0% / 0.245 |
| PSM 11 (sparse text) | 50.0% / 0.328 | 4.3% / 0.794 | 62.5% / 0.402 |

What this shows:

- **Preprocessing matters on photos, not on scans.** On CORD's phone photos it more than halves the
  CER (0.926 → 0.403) and lifts totals 10 points. On SROIE's flat scans the gain is small, and on clean
  synthetic renders raw grayscale is just as good.
- **Denoising is the preprocessing step that matters most.** Removing NL-means raises CER on all three
  sets; replacing it with a median filter costs 13 points of totals on SROIE (the median closes the
  inner stroke of 0/6/8 and merges thin glyphs).
- **Thresholds:** local methods (adaptive Gaussian/mean, Sauvola) beat Otsu on photos (0.41–0.43 vs
  0.54 CER), because one global threshold cannot handle shadows and uneven light. Sauvola is level with
  production; the difference in totals is 2 receipts of 50 on CORD.
- **Reading both images is a safety net:** each single image is worse than the pair on at least one set.
- **Page segmentation is the biggest lever.** PSM 3 and 4 split receipts' two columns (label on the
  left, amount on the right) into separate blocks, so `TOTAL` and its amount end up on different lines:
  synthetic totals fall from 95% to 20%. PSM 11 loses reading order. PSM 6 is right for receipts.
- **Deskew** matters for photos (CORD totals 29.8% → 23.4% without it) and slightly hurts the already
  straight SROIE scans (one receipt, within noise).

Decision: production defaults stay as they are. No alternative is clearly better on all three sets,
and the per-set differences are within a few receipts. Sauvola is the candidate to re-test once a real
Indian photo set exists.

## 4. Image quality vs extraction accuracy

<!-- filled from quality_synthetic / quality_sroie -->
