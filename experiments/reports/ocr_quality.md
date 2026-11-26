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

## 2b. Processing latency

Sequential, uncached run on a quiet 4-CPU container (`sroie_main_parser13-…-r2`, 200 SROIE receipts; the
first `sroie_main_parser13` run overlapped a test run, so its timings are not used):

| stage | mean | p50 | p95 |
|---|---|---|---|
| decode (+ quality measures) | 56 ms | 10 ms | 298 ms |
| preprocess | 271 ms | 223 ms | 504 ms |
| Tesseract (two reads in parallel) | 476 ms | 450 ms | 696 ms |
| parse (correction, extraction, validation) | 14 ms | 14 ms | 20 ms |
| **total** | **816 ms** | **767 ms** | **1,218 ms** |

OCR correction costs about 1 ms per receipt (parse 12.9 → 14.1 ms). Tesseract is 58% of the time.
Without preprocessing (raw grayscale) a CORD receipt takes about 0.5 s instead of 0.7 s; PSM 11 is the
slowest configuration (about 1.5 s on SROIE).

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

`experiments/quality.py` damages each receipt in one controlled way at four severities and re-runs the
whole pipeline, with production preprocessing and with none (raw grayscale). Every receipt is its own
control. Severities are defined for a ~1000 px wide image. Synthetic: 30 held-out receipts
(`quality_synthetic`), with exact text and field labels.

**Synthetic, production preprocessing: share of totals correct (CER in brackets)**

| corruption | level 1 | level 2 | level 3 | level 4 |
|---|---|---|---|---|
| clean | 100% (0.004) | | | |
| Gaussian blur σ = 1 / 2 / 3 / 4.5 px | 97% (0.003) | 80% (0.019) | 10% (0.508) | 0% (0.761) |
| motion blur 5 / 11 / 17 / 25 px | 23% (0.051) | 0% (0.575) | 0% | 0% |
| sensor noise σ = 10 / 20 / 35 / 55 | 97% (0.005) | 93% (0.011) | 80% (0.072) | 17% (0.594) |
| JPEG quality 40 / 20 / 10 / 5 | 97% | 97% | 97% (0.007) | 57% (0.026) |
| downscale 0.7 / 0.5 / 0.35 / 0.25 | 97% | 100% | 100% (0.016) | 60% (0.076) |
| faded (contrast × 0.6 / 0.4 / 0.25 / 0.15) | 100% | 100% | 93% (0.028) | 63% (0.411) |
| dark (brightness × 0.7 / 0.5 / 0.35 / 0.22) | 100% | 100% | 97% | 93% (0.084) |
| shadow depth 0.3 / 0.5 / 0.7 / 0.85 | 87% (0.049) | 57% (0.164) | 50% (0.305) | 30% (0.436) |
| rotation 3° / 8° / 15° / 25° | 97% | 97% | 100% | 97% (0.004) |

What hurts most, in order: **motion blur** (even 5 px drops totals to 23% while CER is only 0.05:
smeared decimal points and digit shapes are exactly what totals and dates need), **Gaussian blur
beyond σ ≈ 2**, **shadows** (the adaptive threshold copes with soft light, not a hard shadow edge across
the amount column), **strong noise**, and **JPEG below quality 10**. Resolution only matters below about
a third of a normal photo. Rotation up to 25° costs nothing because of deskew.

**Real scans (SROIE test, 30 receipts, `quality_sroie`)** - same corruptions on real thermal-print scans
with line-level ground-truth text. Share of totals correct, production preprocessing (raw grayscale in
brackets); clean: 60% (57%).

| corruption | level 1 | level 2 | level 3 | level 4 |
|---|---|---|---|---|
| Gaussian blur | 47% (57%) | 30% (30%) | 10% (23%) | 3% (7%) |
| motion blur | 37% (40%) | 13% (10%) | 7% (10%) | 0% (3%) |
| noise | 63% (57%) | 57% (53%) | 43% (23%) | 13% (7%) |
| JPEG | 60% (60%) | 63% (53%) | 50% (50%) | 43% (53%) |
| downscale | 57% (63%) | 50% (60%) | 53% (30%) | 30% (20%) |
| faded | 53% (57%) | 53% (60%) | 30% (60%) | 13% (60%) |
| dark | 53% (67%) | 53% (60%) | 50% (63%) | 27% (67%) |
| shadow | 47% (33%) | 43% (27%) | 27% (27%) | 20% (23%) |
| rotation | 63% (53%) | 47% (27%) | 53% (13%) | 47% (0%) |

The real scans confirm the synthetic picture, with smaller margins because they start lower:

- **Blur is the main threat**, motion blur most of all: dates go to 0% from 11 px. Raw grayscale is no
  better, so this needs a sharper photo, not more preprocessing.
- **Preprocessing earns its keep on rotation** (25°: 47% vs 0%), **shadows** (level 1: 47% vs 33%),
  **noise** (σ = 35: 43% vs 23%) and **small images** (0.35×: 53% vs 30%).
- **It costs accuracy on faded and dark scans** (worst fading: 13% vs 60%), exactly as on synthetic
  receipts. Raw grayscale holds steady (57-67% at every level), so the loss comes from the fixed-strength
  NL-means and threshold steps, not from the information in the image.
  This is the main open weakness of the current preprocessing; section "A fix that did not transfer"
  explains why the obvious fix was not adopted.
- Measured image quality again predicts errors less well than OCR confidence (Spearman with CER:
  sharpness −0.32, noise −0.26, **mean confidence −0.72**). With the recalibrated hints, 40% of these
  damaged scans are flagged; totals on them are right 17% of the time vs 56% on the rest.

**Preprocessing vs none under damage** (raw grayscale, same images):

- Preprocessing protects against **rotation** (raw: 30% totals at 8°, 0% at 15°), **downscaling**
  (raw CER 0.984 at 0.25×; production 0.076) and **noise** (raw 0% at σ = 55; production 17%).
- It is **worse on faded and very dark photos**: at contrast × 0.15 raw grayscale reads CER 0.013,
  production 0.411. NL-means with a fixed strength smooths away ink that is only a few grey levels from
  the paper.

**A fix that did not transfer.** A contrast stretch before denoising, with or without a noise-adaptive
NL-means strength, fixed faded and dark synthetic photos (CER 0.40 → 0.003) and helped shadows and
noise. On real receipts it made things worse:

| | production 1.0 | + contrast stretch | + stretch + adaptive NL-means |
|---|---|---|---|
| SROIE dev, 60 (`preprocess11_sroie_dev`): CER / total | **0.165** / **65.0%** | 0.194 / 63.3% | 0.199 / 61.7% |
| CORD photos, 50 (`preprocess11_cord`): CER / total | **0.403** / **29.8%** | 0.487 / 25.5% | 0.780 / 27.7% |

Even on synthetic receipts it is a trade, not a win: on the development seed (`quality11_synthetic_dev`,
30 receipts) it lifts the worst fading from 57% to 93% of totals, shadows (level 2) from 60% to 77% and
Gaussian blur (σ = 3) from 7% to 30%, but loses noise σ = 35 (80% → 63%), mild motion blur (27% → 13%)
and the smallest downscale (73% → 60%).

Both stay as opt-in options (`normalize`, `nlmeans_adaptive`); production is unchanged. Triggering the
stretch only on faded photos is not possible with RMS contrast: ordinary SROIE receipts with little ink
have contrast around 20, the same as a badly faded synthetic one. This is the clearest example in the
project of a synthetic-only result that real data overturned.

**Do the quality measures predict failure?** Spearman correlation with CER over 1,110 synthetic images
(production): sharpness −0.39, noise −0.32, contrast +0.06, brightness +0.10, **Tesseract mean word
confidence −0.83**. OCR's own confidence is by far the best predictor. Sharpness is fooled by noise
(grain raises the Laplacian variance) and does not see motion blur, shadows or JPEG blocking at all.

**Retake hints, recalibrated.** The first, hand-set limits flagged 43% of damaged synthetic images and
separated them poorly (totals right on 59% of flagged vs 82% of unflagged). The limits now sit where
accuracy collapses in the table above, and a hint fires when Tesseract's mean confidence is below 60%:

| retake hints | share flagged | totals right if flagged | if not flagged |
|---|---|---|---|
| first limits (synthetic damage study) | 43.5% | 59.0% | 81.8% |
| **recalibrated + OCR confidence** (same images) | 20.8% | 16.5% | 86.5% |
| recalibrated, SROIE test (200 real, undamaged scans) | 7.0% | 21.4% | 63.4% |
| recalibrated, CORD test (95 real photos) | 50.5% | 8.3% | 42.6% |

The limits were set on the held-out synthetic study, so its row is optimistic; the SROIE and CORD rows
use receipts the limits were not set on. A user who sees the hint is looking at a scan that is far more
likely to be wrong.

The first recalibration also kept an "overexposed" hint (mean brightness > 235). Checking it on SROIE
showed it fired on 67% of ordinary scans, because a clean scan is mostly white paper, and barely
predicted errors (57% vs 68% of totals right). It was removed; the OCR-confidence hint covers glare
that actually washes out text.
