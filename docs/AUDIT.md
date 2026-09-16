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

| # | status | what was done |
|---|---|---|
| B1 | done | Scans are stored with `metadata.status = pending` and marked `attached` on save. Adds `DELETE /api/receipts/{id}` (used by "Discard scan") and an hourly cleanup of pending scans older than `ORPHAN_RECEIPT_HOURS`. Tested. |
| B2 | done | `app/pipeline/validate.py` returns `checks` (pass/warn/fail/info with a message); the scan review lists them. |
| B3 | done | Temperature-scaled probability, threshold chosen on validation (0.65), `status: low_confidence` → "Uncategorised" in API and UI. |
| B4 | done | Top contributing tokens (`tfidf × weight`) returned as `explanation` and shown as "because of: …". |
| B5 | done | Retrain is admin-only (`ADMIN_EMAILS`, 403 otherwise) and runs in the thread pool; the model card records user corrections and that the retrained model isn't re-evaluated. |
| B6 | done | Missing, corrupt or incompatible model → `status: unavailable` with the reason and a background rebuild (can be disabled). Tested with missing and corrupt files; the rebuild path was exercised manually. |
| B7 | done | `/api/health` has `status: ok/degraded`, `degraded: [...]` and `model {status, version, error}`. |
| B8 | done | `category_model.card.json` sidecar, `GET /api/model`, Models page. |
| S1 | done | `app/pipeline/` with one module per stage; confidence constants centralised in `confidence.py`; behaviour unchanged (all 52 existing tests passed after the move). |
| S2 | done | Lexicon moved to `app/pipeline/lexicon.py`; `ml/dataset.py` imports it. |
| S3 | done | `experiments/` with configs, runner, recorded environment, dataset hashes and results; stale `ml/metrics.json` and `ml/eval_ocr.py` removed. |
| S4 | done | README rewritten in the required order; LICENSE and CI added. |
| D1 | done | "synthetic data" badges on the Models page; model card `training_data.synthetic: true`; README keeps real and synthetic results in separate tables. |
| D2 | done | Demo user `is_demo`, expenses `demo: true`; "Demo data" badge, demo notice on Overview, "demo" pill on rows. |
| D3 | done | Seeded rows no longer claim a model suggestion (`suggested_category: null`) or zero-priced items. |
| D4 | kept | Static copy on the sign-in page, not presented as data. |
| M1 | done | SROIE (200 test + 150 train-as-dev) and CORD (100) evaluations with field exact/normalised match, CER and word recall. |
| M2 | done | Synthetic dev (seed 42) and held-out test (seed 1234) sets are separate; the parser was frozen before the real-data runs. The later parser 1.2 fix was checked on the SROIE train split; the re-scored test number is labelled post-hoc. |
| M3 | done | Strict split (merchants and item words disjoint) is now the reported one; the shared-item split is kept as a comparison (0.848 → 0.562 macro-F1 for LogReg). |
| M4 | done | Majority and keyword-rule baselines on the same split. |
| M5 | done | Reliability tables, ECE, Brier, log-loss; temperature scaling fitted on validation; threshold chosen on validation (first 90% target attempt kept and documented). |
| M6 | done | Confusion matrix CSV, most-confident-mistake dumps, receipt error files with an automatic cause breakdown, written analysis. |
| M7 | done | Formula documented in `confidence.py` and the README; usefulness measured (unflagged vs flagged total accuracy). Not calibrated: no labelled Indian data. |
| M8 | done | CER and word recall on SROIE and CORD. |
| M9 | done | PSM 4/6/11 and preprocessing ablation on 60 SROIE receipts, raw vs preprocessed on CORD. |
| M10 | done | `AnomalyRule` dataclass, boundary tests, `detail` explanation string; rule exposed on `/api/model`. |
| X1 | done | `ENV=production` refuses placeholder or short secrets; development generates a random per-process secret with a warning; `.env.example` explains generation. |
| X2 | done | Magic-byte sniffing, 40 MP pixel limit (and Pillow's bomb error handled), spooled upload always closed, stored file name no longer client-controlled, `nosniff` on image responses. |
| X3 | done | Failed-login sliding window per email + IP, 429 with `Retry-After`. In-process only (noted). |
| X4 | done | See B5. |
| X5 | done | Request log line (method, path, status, ms), no bodies, headers or query strings; scan log contains sizes and confidences, not receipt text. |
| X6 | kept | Already fine; CORS methods and headers narrowed. |
| U1 | done | Abstention and explanation UI (see B3/B4). |
| U2 | done | Checks list on the scan review. |
| U3 | done | Models page. |
| U4 | done | "What OCR read" view: cleaned image with per-word boxes, low-confidence words highlighted. |
| U5 | done | Confirm dialog, toasts, skeleton loaders. |
| U6 | done | See D2. |
| T1 | done | vitest + Testing Library: 16 tests. |
| T2 | done | `tests/test_robustness.py` and additions to the ML/parser tests. |
| T3 | done, not run | `.github/workflows/ci.yml` (MongoDB service, Tesseract from apt, pytest; npm test + build). It couldn't be run from the build machine. |

Not done: learned merchant-line classifier, stricter arithmetic confirmation, locale-aware amounts
(future work, from the error analysis); a labelled Indian receipt set (data not available).
