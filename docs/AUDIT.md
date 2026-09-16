# SpendLens audit (Phase 2, step 0)

Written before any Phase 2 change, from a fresh read of the code at the baseline commit
(`643a1fe`). The Resolution section at the end records what was done for each item.

## 1. Broken or incomplete features

| # | Finding | Where |
|---|---|---|
| B1 | Photos scanned but never saved as an expense stay in GridFS forever (orphans). | `routers/receipts.py` |
| B2 | Validation results are computed but thrown away. The arithmetic check (subtotal + tax + round-off vs total) only nudges the confidence, and the user is never told *why* a field is orange. | `services/parser.py::reconcile_total` |
| B3 | The category model has no abstention: a 0.18-probability guess is pre-selected just like a 0.95 one. | `services/classifier.py`, `ExpenseForm.tsx` |
| B4 | No explanation of why a category was suggested. | same |
| B5 | `POST /api/categories/retrain` lets any signed-in user retrain the **global** model, synchronously in the request, from every user's corrections. This is a poisoning risk and blocks a worker for about 10 s. | `routers/categories.py` |
| B6 | If the model file is missing or unreadable, startup retrains synchronously. If that fails (for example `ml/` isn't importable), the app crashes instead of reporting a degraded state. | `CategoryModel.load` |
| B7 | `/api/health` doesn't say whether the classifier is degraded or why. | `main.py` |
| B8 | No model metadata endpoint or model card. | — |

## 2. Structure and duplication

| # | Finding |
|---|---|
| S1 | The receipt pipeline stages aren't explicit. `ocr.py` mixes decoding, preprocessing and OCR. `parser.py` mixes text normalisation, field extraction, validation and confidence. The confidence formula is spread over magic numbers. |
| S2 | `app/services/parser.py` imports `ml.dataset` to get the merchant list (app → training code dependency). |
| S3 | Metrics live in `backend/ml/metrics.json` with no run id, git commit, library versions or dataset hash, and there's no `experiments/` structure. |
| S4 | The README repeats ML details in several sections and has no Technical Deep Dive, env table, licence or CI. |

## 3. Placeholder, demo or synthetic data, and where it shows up

| # | Finding |
|---|---|
| D1 | Every ML number is from **synthetic** data (generated merchants/items, generated receipt photos). The README says so, but the UI doesn't. |
| D2 | The demo account (`scripts/seed.py`, "Aditi Rao") shows seeded expenses with no marker in the UI that they are demo data. |
| D3 | Seed line items have `price: 0` and `suggested_category == category` for every row (it looks like perfect model accuracy). |
| D4 | The login page's "sample" ledger lines are decorative. Acceptable, but they must not be read as real data; they are static copy. |

## 4. ML weaknesses

| # | Finding |
|---|---|
| M1 | **No real-data evaluation.** The parser has only been measured on receipts made by our own generator. |
| M2 | **Tuned on the test set.** The parser was debugged against the same 30 synthetic receipts (seed 42) that it's reported on, so the 100% total accuracy is a dev-set number, not a held-out one. |
| M3 | The classifier's held-out split holds out *merchants*, but item vocabularies are shared across splits, and items are very indicative. The overall score is optimistic; the "merchant name only" figure is the honest one. |
| M4 | No baselines (majority class, keyword rules) for the classifier. |
| M5 | Probabilities are uncalibrated (`LogisticRegression(C=8, class_weight="balanced")` tends to be over- or under-confident). No reliability table, ECE or Brier score. No validation split for choosing a confidence threshold. |
| M6 | No confusion matrix and no error-analysis dump for either the classifier or the parser. |
| M7 | Field confidence is heuristic and undocumented (OCR confidence × keyword strength × position, plus arithmetic bumps). |
| M8 | No OCR character error rate (CER) is measured anywhere. |
| M9 | PSM (Tesseract page segmentation mode) choice (`--psm 6`) was never compared with alternatives. |
| M10 | The anomaly threshold (3.5 / 2×) is hard-coded, and there's no test at the exact boundary. |

## 5. Security

| # | Finding |
|---|---|
| X1 | The JWT secret defaults to `change-me-in-production` and the app starts silently with it. |
| X2 | Uploads trust the `Content-Type` header. There's no magic-byte check and no explicit decompression-bomb guard (`Image.MAX_IMAGE_PIXELS`); Pillow only warns up to 2× its default. |
| X3 | No login rate limiting (bcrypt makes brute force slow, but that's all). |
| X4 | Global retrain endpoint (see B5). |
| X5 | No logging configuration. Nothing sensitive is logged today, but there's also no request or error logging to rely on. |
| X6 | OK already: CORS restricted to configured origins; every query filtered by `user_id`; regex search input escaped; no user-controlled filesystem paths (GridFS only); upload size capped by reading `limit + 1` bytes. |

## 6. UI/UX gaps

| # | Finding |
|---|---|
| U1 | No low-confidence / "Uncategorised" state for the category suggestion; no top contributing words. |
| U2 | Validation problems (numbers not adding up, future date) aren't shown. |
| U3 | No model/about panel, and no statement in the UI that the models were trained or evaluated on synthetic data. |
| U4 | No OCR preview beyond a raw text dump; can't see *where* the text was read. |
| U5 | Deletes use `window.confirm`; no toasts; loading states are text, not skeletons. |
| U6 | Demo account isn't labelled as demo (see D2). |

## 7. Test gaps

| # | Finding |
|---|---|
| T1 | No frontend unit tests (vitest). |
| T2 | No robustness tests for: missing model file, corrupt model, fake image with image content type (magic bytes), decompression bomb, empty image, tiny/low-quality image, low-confidence category path. |
| T3 | No CI. |

## Prioritised plan

1. Make the receipt pipeline stages explicit (`app/pipeline/`: preprocess → OCR → normalise → extract → validate/confidence → record), without changing behaviour. The existing tests must still pass. Surface validation results in the API.
2. Real evaluation: SROIE (`rth/sroie-2019-v2` test split) and CORD-v2 (test split) downloaders, a manifest with licence and hash, field exact and normalised match, CER, ablations (preprocessing on/off, PSM 4/6/11), and an error-analysis dump. Separate synthetic dev and test seeds.
3. `experiments/` package: configs, `run.py`, results with environment/commit/dataset hash, reports.
4. Category model: baselines on the same split, calibration (reliability table, ECE, Brier; sigmoid calibration fit on a validation split), abstention threshold picked on validation, top-token explanation, model card sidecar plus `/api/model`.
5. Anomaly: configurable, unit-tested threshold and explanation.
6. Security: JWT placeholder guard, magic bytes + pixel limit, login rate limit, logging, admin-gated retrain, orphan cleanup.
7. UI: abstention and explanation, validation messages, model panel with synthetic/real labels, OCR box overlay, demo badge, toasts, confirm dialog, skeletons, vitest.
8. README rewrite, LICENSE, CI, screenshots, final full test run.

## Resolution

*(filled in at the end of Phase 2)*
