"""Category classifier: baselines, main model, calibration, abstention threshold, error analysis,
and (optionally) the production artifact + model card.

    python -m experiments.run --config experiments/configs/category_main.yaml
    python -m ml.train_classifier            # same thing, from the backend folder

Split (ml/dataset.py::build_splits): merchants AND item words disjoint across train / val / test.
Data is SYNTHETIC (generated from a hand-written Indian merchant/item lexicon).

Why these metrics: classes are roughly balanced but not equal, and every category matters to the user,
so macro-F1 is the headline next to accuracy. The model's probability is shown to the user and drives
abstention, so calibration (ECE, Brier, reliability table) is measured before and after temperature
scaling. The abstention threshold is chosen on validation only; test is touched once.
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, log_loss

from app.categories import MODEL_CATEGORIES as CATEGORIES
from ml import dataset
from ml.baselines import KeywordRules
from ml.calibration import brier, fit_temperature, pick_threshold, reliability, softmax
from ml.pipeline import make_cnb, make_logreg

ART = Path(__file__).resolve().parent / "artifacts"
MODEL = ART / "category_model.joblib"
CARD = ART / "category_model.card.json"
FEATURES_VERSION = "tfidf-word12-char24-v1"

FACTORIES = {
    "majority": lambda: DummyClassifier(strategy="most_frequent"),
    "keyword_rules": KeywordRules,
    "complement_nb": make_cnb,
    "logreg": make_logreg,
}


def probs_for(model, X, name: str) -> np.ndarray:
    return model.predict_proba(X)


def logits_in_order(model, X) -> np.ndarray:
    """Per-class scores whose softmax is the model's probability, columns in CATEGORIES order
    (sklearn sorts classes by name). LogReg: decision_function. ComplementNB: log-probabilities
    (a per-row constant shift, which softmax ignores)."""
    raw = model.decision_function(X) if hasattr(model, "decision_function") else model.predict_log_proba(X)
    return aligned(raw, list(model.classes_))


CALIBRATABLE = ("logreg", "complement_nb")
ALGORITHMS = {
    "logreg": "TF-IDF (word 1-2 grams + char_wb 2-4 grams) -> multinomial LogisticRegression",
    "complement_nb": "TF-IDF (word 1-2 grams + char_wb 2-4 grams) -> ComplementNB",
}


def aligned(probs: np.ndarray, classes: list[str]) -> np.ndarray:
    """Re-order probability columns to CATEGORIES order (dummy/rules may know fewer classes)."""
    out = np.zeros((probs.shape[0], len(CATEGORIES)))
    for j, c in enumerate(classes):
        out[:, CATEGORIES.index(c)] = probs[:, j]
    return out


def score(y: list[str], probs: np.ndarray, kinds: list[str]) -> dict:
    y_idx = np.array([CATEGORIES.index(c) for c in y])
    pred_idx = probs.argmax(1)
    pred = [CATEGORIES[i] for i in pred_idx]
    conf = probs.max(1)
    correct = pred_idx == y_idx
    ece, table = reliability(conf, correct)
    by_kind = {}
    for k in sorted(set(kinds)):
        m = np.array([kk == k for kk in kinds])
        by_kind[k] = {"n": int(m.sum()), "accuracy": round(float(correct[m].mean()), 4)}
    return {
        "accuracy": round(accuracy_score(y, pred), 4),
        "macro_f1": round(f1_score(y, pred, average="macro", labels=CATEGORIES, zero_division=0), 4),
        "log_loss": round(log_loss(y_idx, np.clip(probs, 1e-12, 1), labels=list(range(len(CATEGORIES)))), 4),
        "brier": round(brier(probs, y_idx), 4),
        "ece": round(ece, 4),
        "mean_confidence": round(float(conf.mean()), 4),
        "by_input_kind": by_kind,
        "per_class": {k: {m: round(v[m], 3) for m in ("precision", "recall", "f1-score", "support")}
                      for k, v in classification_report(y, pred, labels=CATEGORIES, output_dict=True,
                                                         zero_division=0).items() if k in CATEGORIES},
        "_reliability": table,
    }


def run(cfg: dict, run_dir: Path) -> dict:
    seed = cfg.get("seed", 7)
    sp = dataset.build_splits(seed=seed, per_merchant=cfg.get("per_merchant", 30),
                              holdout_items=cfg.get("holdout_items", True))
    tr, va, te = sp["train"], sp["val"], sp["test"]
    out: dict = {
        "dataset": {"name": "synthetic-indian-merchants", "synthetic": True,
                    "generator": "backend/ml/dataset.py (lexicon: backend/app/pipeline/lexicon.py)",
                    "split": "merchants and item words disjoint across train/val/test" if cfg.get("holdout_items", True)
                    else "merchants disjoint; item words shared",
                    "sizes": {k: len(v["X"]) for k, v in sp.items()},
                    "sha256": {k: dataset.fingerprint(v["X"], v["y"]) for k, v in sp.items()},
                    "seed": seed},
        "models": {},
    }
    fitted = {}
    for name in cfg.get("models", list(FACTORIES)):
        t = time.perf_counter()
        m = FACTORIES[name]().fit(tr["X"], tr["y"])
        fit_s = time.perf_counter() - t
        fitted[name] = m
        res = {"fit_seconds": round(fit_s, 2)}
        for split_name, split in (("val", va), ("test", te)):
            res[split_name] = score(split["y"], aligned(probs_for(m, split["X"], name), list(m.classes_)), split["kind"])
        out["models"][name] = res
        print(f"  {name:14} test acc={res['test']['accuracy']:.3f} macroF1={res['test']['macro_f1']:.3f} "
              f"ECE={res['test']['ece']:.3f}", flush=True)

    # --- calibration + abstention for the selected model (validation only) ---
    sel = cfg.get("selected", "auto")
    if sel == "auto":  # decided on validation, never on test
        sel = max((n for n in CALIBRATABLE if n in fitted),
                  key=lambda n: (out["models"][n]["val"]["macro_f1"], n == "logreg"))
    out["selection"] = {"rule": "highest validation macro-F1 among " + ", ".join(CALIBRATABLE),
                        "val_macro_f1": {n: out["models"][n]["val"]["macro_f1"] for n in CALIBRATABLE if n in fitted}}
    m = fitted[sel]
    y_va = np.array([CATEGORIES.index(c) for c in va["y"]])
    logits_va = logits_in_order(m, va["X"])
    T = fit_temperature(logits_va, y_va)
    p_va = softmax(logits_va / T)
    correct_va = p_va.argmax(1) == y_va
    tau, rc_val = pick_threshold(p_va.max(1), correct_va, cfg.get("target_accuracy", 0.9))
    p_te = softmax(logits_in_order(m, te["X"]) / T)
    cal_test = score(te["y"], p_te, te["kind"])
    y_te = np.array([CATEGORIES.index(c) for c in te["y"]])
    conf_te = p_te.max(1)
    correct_te = p_te.argmax(1) == y_te
    keep = conf_te >= tau
    _, rc_test = pick_threshold(conf_te, correct_te, 2.0)  # table only
    out["calibration"] = {
        "method": "temperature scaling fitted on validation (NLL)",
        "temperature": round(T, 4),
        "test_before": {k: out["models"][sel]["test"][k] for k in ("ece", "brier", "log_loss", "mean_confidence")},
        "test_after": {k: cal_test[k] for k in ("ece", "brier", "log_loss", "mean_confidence")},
        "reliability_test_before": out["models"][sel]["test"]["_reliability"],
        "reliability_test_after": cal_test["_reliability"],
    }
    out["abstention"] = {
        "target_accuracy_on_val": cfg.get("target_accuracy", 0.9),
        "threshold": tau,
        "val_risk_coverage": rc_val,
        "test_risk_coverage": rc_test,
        "test_at_threshold": {"coverage": round(float(keep.mean()), 4),
                              "accuracy_on_accepted": round(float(correct_te[keep].mean()), 4) if keep.any() else None,
                              "accuracy_on_abstained": round(float(correct_te[~keep].mean()), 4) if (~keep).any() else None},
    }

    # --- confusion matrix + error analysis (test, selected model, calibrated) ---
    pred_te = [CATEGORIES[i] for i in p_te.argmax(1)]
    cm = confusion_matrix(te["y"], pred_te, labels=CATEGORIES)
    with open(run_dir / "confusion_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["true \\ predicted"] + CATEGORIES)
        for c, row in zip(CATEGORIES, cm):
            w.writerow([c] + list(map(int, row)))
    pairs = Counter((t, p) for t, p in zip(te["y"], pred_te) if t != p)
    out["top_confusions"] = [{"true": t, "predicted": p, "count": n} for (t, p), n in pairs.most_common(8)]
    wrong = [i for i in range(len(pred_te)) if pred_te[i] != te["y"][i]]
    wrong.sort(key=lambda i: -conf_te[i])
    with open(run_dir / "errors.jsonl", "w") as f:
        for i in wrong:
            f.write(json.dumps({"text": te["X"][i], "true": te["y"][i], "predicted": pred_te[i],
                                "confidence": round(float(conf_te[i]), 3), "kind": te["kind"][i],
                                "merchant": te["merchant"][i], "abstained": bool(conf_te[i] < tau)},
                               ensure_ascii=False) + "\n")
    md = [f"# Category classifier - most confident mistakes (test, {sel}, calibrated)", "",
          f"{len(wrong)} wrong of {len(pred_te)}. Abstention threshold {tau}: "
          f"{sum(conf_te[i] >= tau for i in wrong)} of these mistakes would still be shown as a suggestion.", "",
          "| text | true | predicted | conf | kind |", "|---|---|---|---|---|"]
    for i in wrong[:30]:
        md.append(f"| {te['X'][i][:70].replace('|', '/')} | {te['y'][i]} | {pred_te[i]} | {conf_te[i]:.2f} | {te['kind'][i]} |")
    md += ["", "## Top confusions", "", "| true | predicted | count |", "|---|---|---|"]
    md += [f"| {c['true']} | {c['predicted']} | {c['count']} |" for c in out["top_confusions"]]
    (run_dir / "errors.md").write_text("\n".join(md) + "\n")
    for res in out["models"].values():  # keep metrics.json readable: tables live in the calibration block
        for s in ("val", "test"):
            res[s].pop("_reliability", None)
    out["selected"] = sel
    out["run_id"] = run_dir.name

    if cfg.get("save_model"):
        out["artifact"] = save_production_model(cfg, card_evaluation(out, sel), sel, T, tau)
    return out


def card_evaluation(results: dict, kind: str) -> dict:
    return {
        "run_id": results.get("run_id"),
        "dataset": "synthetic; " + results["dataset"]["split"],
        "test_size": results["dataset"]["sizes"]["test"],
        "test_accuracy": results["models"][kind]["test"]["accuracy"],
        "test_macro_f1": results["models"][kind]["test"]["macro_f1"],
        "test_merchant_only_accuracy": results["models"][kind]["test"]["by_input_kind"].get("merchant_only", {}).get("accuracy"),
        "test_ece_before_calibration": results["calibration"]["test_before"]["ece"],
        "test_ece_after_calibration": results["calibration"]["test_after"]["ece"],
        "test_coverage_at_threshold": results["abstention"]["test_at_threshold"]["coverage"],
        "test_accuracy_at_threshold": results["abstention"]["test_at_threshold"]["accuracy_on_accepted"],
        "selection": results.get("selection"),
        "baselines_test_macro_f1": {k: v["test"]["macro_f1"] for k, v in results["models"].items()},
    }


def save_production_model(cfg: dict, evaluation: dict, kind: str, T: float, tau: float, extra_X=None, extra_y=None,
                          feedback_rows: int = 0, path: Path | None = None) -> dict:
    """Refit the selected model on all synthetic merchants (+ optional user corrections) and write the
    artifact and its model card. Temperature and threshold come from the validation split of the
    evaluation run and are reused - the card says so."""
    X, y = dataset.build_full(seed=cfg.get("seed", 7))
    if extra_X:
        X, y = X + list(extra_X), y + list(extra_y)
    t = time.perf_counter()
    model = FACTORIES[kind]().fit(X, y)
    now = datetime.now(timezone.utc)
    version = now.strftime("cat-%Y%m%d-%H%M%S")
    params = model.named_steps["clf"].get_params()
    card = {
        "model": "expense category classifier",
        "version": version,
        "trained_at": now.isoformat(timespec="seconds"),
        "algorithm": ALGORITHMS[kind],
        "kind": kind,
        "hyperparameters": {k: v for k, v in params.items() if isinstance(v, (int, float, str, bool, type(None)))},
        "features_version": FEATURES_VERSION,
        "seed": cfg.get("seed", 7),
        "classes": CATEGORIES,
        "training_data": {
            "name": "synthetic-indian-merchants", "synthetic": True,
            "size": len(X), "user_corrections": feedback_rows,
            "sha256": dataset.fingerprint(X, y),
            "description": "Generated from a hand-written lexicon of Indian merchants and bill items "
                           "(backend/app/pipeline/lexicon.py) with simulated OCR noise.",
        },
        "calibration": {"method": "temperature scaling", "temperature": round(T, 4),
                        "fitted_on": "validation split of the evaluation run (train-split model); reused for this refit"},
        "run_config": {k: cfg.get(k) for k in ("name", "seed", "per_merchant", "holdout_items", "target_accuracy")},
        "abstention": {"threshold": tau, "rule": "suggest 'Uncategorised' when calibrated top probability < threshold",
                       "chosen_for": f"validation accuracy >= {cfg.get('target_accuracy', 0.9)} on accepted predictions"},
        "evaluation": evaluation,
        "libraries": {"scikit-learn": sklearn.__version__, "numpy": np.__version__},
        "intended_use": "Suggest a spending category for a personal expense from merchant name and item text. "
                        "The user confirms every suggestion.",
        "limitations": [
            "Trained and evaluated on synthetic data only - no real labelled Indian expense data was available.",
            "An unseen merchant name with no item text is often ambiguous; expect many abstentions there.",
            "English/romanised text only.",
            "Per-user corrections override the model for known merchants; the global model only changes on retrain.",
        ],
    }
    model_path = Path(path) if path else MODEL
    card_path = model_path.with_name(model_path.name.replace(".joblib", ".card.json"))
    model_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"model": model, "kind": kind, "temperature": T, "abstain_threshold": tau,
              "version": version, "sklearn": sklearn.__version__, "feedback_rows": feedback_rows,
              "trained_on": len(X)}
    tmp = model_path.with_suffix(".tmp")
    joblib.dump(bundle, tmp, compress=3)
    tmp.replace(model_path)  # atomic swap: a reader never sees a half-written file
    card["fit_seconds"] = round(time.perf_counter() - t, 2)
    card["artifact_bytes"] = model_path.stat().st_size
    card_path.write_text(json.dumps(card, indent=2) + "\n")
    return {"path": model_path.name, "version": version, "bytes": model_path.stat().st_size}
