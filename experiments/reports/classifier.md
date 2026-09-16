# Category classifier: baselines, calibration, abstention

All data here is **synthetic**: text generated from a hand-written lexicon of Indian merchants and
bill items with simulated OCR noise. No labelled real expense data was available.
Runs: `category_main-20260916` (strict split, production model),
`category_shared_items-20260916`, `category_target90-20260916`.

## Split

Merchants **and** item words are disjoint across train (5,460), validation (945) and test (1,245).
The phase-1 split held out merchants but shared item words. On that split LogReg scored macro-F1
0.848; on the strict split it scores 0.562. The phase-1 number was mostly measuring memorised item words.

## Baselines (test, strict split)

| model | accuracy | macro-F1 | log-loss | Brier | ECE | merchant name only |
|---|---|---|---|---|---|---|
| majority class | 12.0% | 0.021 | 24.302 | 1.759 | 0.879 | 10.3% |
| keyword rules (hand-written) | 45.9% | 0.470 | 13.574 | 1.012 | 0.526 | 27.4% |
| TF-IDF + LogisticRegression | 57.3% | 0.562 | 1.366 | 0.551 | 0.107 | 34.2% |
| **TF-IDF + ComplementNB** (selected on validation macro-F1: 0.482 vs 0.476) | **58.1%** | **0.575** | 1.365 | **0.534** | 0.101 | 31.9% |

The two learned models are within noise of each other. Both beat hand-written rules by about 10
points of macro-F1. The rules' probabilities are nearly useless (log-loss 13.6) because a keyword
hit gives probability 1.0.

## Calibration

Temperature scaling on validation found T = 1.96: the raw ComplementNB probabilities were
over-confident. On test, ECE went 0.101 → 0.091 and log-loss 1.365 → 1.333; Brier went slightly up
(0.534 → 0.540). The reliability table after scaling (`summary.md`) shows the model is now
*under*-confident between 0.5 and 0.8 (about 0.55–0.75 stated, 0.85–0.87 observed) and roughly right
at the extremes. A single temperature can't fix both ends; isotonic regression would need a bigger
validation set than 945 examples. The abstention threshold is chosen on these scaled scores, so the
miscalibration is absorbed by where the threshold sits.

## Abstention

The threshold is the smallest confidence at which **validation** accuracy reaches the target.

- The first attempt used a 90% target (`category_target90`). Validation never reaches 90%, and the
  code at the time fell back to 0.95, covering 3.9% of test examples, which is unusable. That fallback
  is now "best validation accuracy", and the target is 80%. This change was made after seeing that
  run's test table; the threshold itself still comes from validation.
- Result: threshold 0.65. On test the model **suggests for 34.3% of examples and is right 89.9% of the
  time**. The other 65.7% are left "Uncategorised"; its best guess there would have been right only
  41.6% of the time.

## Error analysis (`category_main-20260916/errors.md`)

The most confident mistakes are mostly the lexicon's fault, not the model's:
- "Sapna Book House" is an Education merchant, and "Sapna Book House Stationery" is a Shopping
  merchant. The model can't separate them.
- "Amazon Prime" (Entertainment) vs "Amazon" (Shopping). "Swiggy" (Food) vs "Swiggy Instamart"
  (Groceries).
- "Delhi Jal Board" → Transport (shares character n-grams with "Delhi Metro"). "Blue Dart" → Food
  (close to "Blue Tokai").
- Top confusions: Entertainment → Bills & Utilities (35) and → Groceries (34). The held-out
  Entertainment item words ("monthly plan", "subscription", "family pack") look like recharge plans
  and grocery packs.

This is also the case for per-user merchant overrides: once a user corrects "Swiggy" to Food, the
model is no longer asked.

## Limits

- Synthetic text only. Real merchant strings (UPI payee names, abbreviations like "RELIANCE RETAIL
  LTD-BLR") will behave differently.
- 945 validation examples from about 6 merchants per class make the threshold choice noisy.
- The production model is refit on all synthetic merchants and reuses T and the threshold from the
  train-split model, so its real confidence is probably a little higher than stated.
