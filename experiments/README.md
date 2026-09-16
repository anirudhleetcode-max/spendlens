# Experiments

Every number in the project README comes from a run in `results/`. Runs are created only by
`run.py`, never edited by hand (the one renamed run says why in its `NOTE.md`).

```bash
# from the project root, with backend requirements-dev installed
python -m experiments.datasets download sroie        # real data (see data/README.md)
python -m experiments.datasets download sroie_train
python -m experiments.datasets download cord
python -m experiments.run --config experiments/configs/sroie_main.yaml
python -m experiments.analyse_errors experiments/results/<run_id>   # also run automatically
python -m experiments.summarise                      # rebuilds reports/summary.md
```

A run writes `results/<name>-<YYYYMMDD>[-rN]/`:

| file | contents |
|---|---|
| `config.yaml` | the exact config used |
| `env.json` | UTC timestamp, git commit and dirty flag, Python/library/Tesseract versions, CPU count, parser and preprocessing versions |
| `metrics.json` | results + dataset name, SHA-256, subset-id hash, synthetic flag |
| `errors.jsonl`, `errors.md` | worst failures, most confident first |
| `errors_breakdown.json` | receipt errors grouped by cause (`analyse_errors.py`) |
| `per_receipt.jsonl` | per-receipt scores (receipt runs) |
| `confusion_matrix.csv` | classifier runs |

`git_dirty: true` means tracked files had uncommitted edits when the run started. For the runs marked
dirty here, those edits were in files the run doesn't execute (UI, classifier serving code, run-id
naming); `git diff dc4fc2f 4462f0a -- backend/app/pipeline/normalise.py backend/app/pipeline/ocr.py
backend/app/pipeline/preprocess.py` is empty, and the parser change between them is versioned
(`parser_version` in every result).

OCR output is cached in `data/cache/ocr/<dataset>/<ocr settings>/<id>.json` (git-ignored), so a
parser-only change can be re-scored in seconds.

## Adding an experiment

1. Copy a config in `configs/`. Receipt runs: `task: receipt_extraction`, a `dataset` (`sroie`,
   `sroie_train`, `cord`, `synthetic`), `n`, `seed` and one or more `variants` with `ocr` settings
   (`preprocess`, `dual`, `psm`) and optional `parser` options. Classifier runs:
   `task: category_classifier`.
2. A new dataset needs an entry in `datasets.SOURCES` (URL, licence, SHA-256) and a loader that yields
   the record shape documented there.
3. Run it, run `summarise`, commit the result folder with the code it was run from.

## Runs

| run | data | what it answers | result (see `reports/summary.md`) |
|---|---|---|---|
| `sroie_main-20260916` | SROIE test, 200, **real** | How well does the pipeline read unseen real receipts? Scored blind (parser 1.1). | merchant 23.5%, date 78.5%, total 48.5%, CER 0.197 |
| `sroie_ablation-20260916` | SROIE test, first 60, **real** | Which OCR settings matter? | preprocessing lowers CER (0.173 vs 0.208 raw) but raw grayscale got more totals right (53.3% vs 48.3%); PSM 11 is worst on CER |
| `sroie_dev_parser-20260916` | SROIE **train** split, 150, **real** (dev set) | Does the tax-inclusive-total fix (parser 1.2) help on data it wasn't designed on? | total 56.0% → 68.7%; merchant and date unchanged |
| `sroie_main_parser12-20260916` | SROIE test, 200, **real** | Test score after the fix. **Post-hoc** (the fix came from this set's errors). | total 57.5% |
| `cord_main-20260916`, `-r2` | CORD test, 100, **real** | Out-of-domain photos (Indonesia). r2 = parser 1.2. | total 24.2%, CER 0.534 (raw: 0.926) |
| `synthetic_dev-20260916`, `-r2` | generated, 30, **synthetic** | The set the parser was developed on. | 100% / 100% / 100% (optimistic by construction) |
| `synthetic_test-20260916`, `-r2` | generated, 60, **synthetic** | Held-out generator seed. | merchant 100%, date 100%, total 96.7% |
| `category_main-20260916` | generated text, **synthetic**, shops and item words held out | Baselines, calibration, abstention; writes the production model. | ComplementNB macro-F1 0.575 (LogReg 0.562, keyword rules 0.470, majority 0.021); at threshold 0.65 it suggests for 34.3% of test examples with 89.9% accuracy |
| `category_shared_items-20260916` | same, item words shared | How much does the easier phase-1 split flatter the model? | LogReg macro-F1 0.848 (vs 0.562 strict) |
| `category_target90-20260916` | same as main, 90% target | First abstention attempt, kept for the record. | threshold fell back to 0.95, 3.9% coverage (see NOTE.md) |

Reports: `reports/summary.md` (generated tables), `reports/receipts.md` and `reports/classifier.md`
(written analysis).
