"""Category suggestion (pipeline stage 7).

    per-user merchant override (learned from corrections)      -> status "override"
    else TF-IDF + linear model, temperature-scaled probability  -> status "confident"
         ... below the abstention threshold                     -> status "low_confidence" (UI: Uncategorised)
    model missing / failed to load                              -> status "unavailable"

Explanation: both candidate models are linear in the TF-IDF features, so the contribution of a
feature to class k is tfidf_value x weight[k]. The top positive word-level contributions are returned
("petrol", "speed petrol"); character n-grams are only shown when no word feature contributes.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from ..categories import MODEL_CATEGORIES, UNCATEGORISED
from ..config import get_settings
from ..utils import merchant_key

log = logging.getLogger(__name__)
DEFAULT_THRESHOLD = 0.5


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


class CategoryModel:
    def __init__(self, path: str, auto_rebuild: bool = True):
        self.path = Path(path)
        self.card_path = self.path.with_name(self.path.name.replace(".joblib", ".card.json"))
        self._lock = threading.Lock()
        self.bundle: dict | None = None
        self.card: dict | None = None
        self.status = "loading"
        self.error: str | None = None
        self._feature_names: np.ndarray | None = None
        self.load(auto_rebuild=auto_rebuild)

    # ---------- loading ----------

    def load(self, auto_rebuild: bool = True) -> None:
        import sklearn
        try:
            if not self.path.exists():
                raise FileNotFoundError(f"model file not found: {self.path.name}")
            bundle = joblib.load(self.path)
            if bundle.get("sklearn") != sklearn.__version__:
                raise RuntimeError(f"model was saved with scikit-learn {bundle.get('sklearn')}, "
                                   f"this environment has {sklearn.__version__}")
            names = bundle["model"].named_steps["tfidf"].get_feature_names_out()
            card = json.loads(self.card_path.read_text()) if self.card_path.exists() else None
        except Exception as e:  # missing, corrupt, incompatible pickle
            self._degrade(str(e))
            if auto_rebuild:
                threading.Thread(target=self._rebuild, name="category-model-rebuild", daemon=True).start()
            return
        with self._lock:
            self.bundle, self.card, self._feature_names = bundle, card, names
            self.status, self.error = "ready", None
        log.info("category model %s loaded (%s)", bundle.get("version"), bundle.get("kind"))

    def _degrade(self, reason: str) -> None:
        with self._lock:
            self.bundle, self._feature_names = None, None
            self.status, self.error = "unavailable", reason
        log.warning("category model unavailable: %s", reason)

    def _rebuild(self) -> None:
        """Pickles are tied to the scikit-learn version: retrain locally (seconds) instead of failing."""
        try:
            with self._lock:
                self.status = "rebuilding"
            from ml.evaluate_classifier import save_production_model
            old = self.card or (json.loads(self.card_path.read_text()) if self.card_path.exists() else {})
            cfg = old.get("run_config") or {"seed": 7, "target_accuracy": 0.9}
            evaluation = dict(old.get("evaluation") or {"note": "Experiment not run in this environment."})
            kind = old.get("kind", "logreg")
            T = (old.get("calibration") or {}).get("temperature", 1.0)
            tau = (old.get("abstention") or {}).get("threshold", DEFAULT_THRESHOLD)
            save_production_model(cfg, evaluation, kind, T, tau, path=self.path)
            self.load(auto_rebuild=False)
        except Exception as e:
            self._degrade(f"rebuild failed: {e}")

    @property
    def ready(self) -> bool:
        return self.status == "ready" and self.bundle is not None

    @property
    def threshold(self) -> float:
        return float((self.bundle or {}).get("abstain_threshold", DEFAULT_THRESHOLD))

    def info(self) -> dict:
        return {"status": self.status, "error": self.error,
                "version": (self.bundle or {}).get("version"), "kind": (self.bundle or {}).get("kind"),
                "threshold": self.threshold if self.bundle else None,
                "temperature": (self.bundle or {}).get("temperature"),
                "feedback_rows": (self.bundle or {}).get("feedback_rows"), "card": self.card}

    # ---------- inference ----------

    def predict(self, text: str) -> dict | None:
        """None when unavailable. Otherwise calibrated probabilities (MODEL_CATEGORIES order) + explanation."""
        with self._lock:
            bundle, names = self.bundle, self._feature_names
        if bundle is None or not text.strip():
            return None
        model = bundle["model"]
        clf = model.named_steps["clf"]
        x = model.named_steps["tfidf"].transform([text])
        raw = clf.decision_function(x)[0] if hasattr(clf, "decision_function") else clf.predict_log_proba(x)[0]
        classes = list(clf.classes_)
        logits = np.array([raw[classes.index(c)] for c in MODEL_CATEGORIES])
        probs = _softmax(logits / float(bundle.get("temperature", 1.0)))
        k = int(probs.argmax())
        return {"probs": probs, "top": MODEL_CATEGORIES[k], "p": float(probs[k]),
                "explanation": self._explain(clf, x, classes.index(MODEL_CATEGORIES[k]), names)}

    @staticmethod
    def _explain(clf, x, class_idx: int, names, k: int = 5) -> list[dict]:
        weights = clf.coef_[class_idx] if hasattr(clf, "coef_") else clf.feature_log_prob_[class_idx]
        row = x.tocsr()
        idx, vals = row.indices, row.data
        if len(idx) == 0:
            return []
        contrib = vals * np.asarray(weights)[idx]
        if not hasattr(clf, "coef_"):  # NB weights are all negative-ish; rank relative to the class mean
            contrib = vals * (np.asarray(weights)[idx] - np.asarray(clf.feature_log_prob_)[:, idx].mean(0))
        order = np.argsort(-contrib)
        words: list[dict] = []
        chars: dict[str, dict] = {}
        for j in order:
            if contrib[j] <= 0:
                break
            kind, _, tok = str(names[idx[j]]).partition("__")
            tok = tok.strip()
            item = {"token": tok, "weight": round(float(contrib[j]), 3), "type": kind}
            if kind == "word":
                words.append(item)
            elif len(tok) >= 3 and tok not in chars:
                chars[tok] = item
        out = words[:k]
        if len(out) < 2:  # e.g. a single unseen word: show the word pieces that carried the decision
            shown = " ".join(w["token"] for w in out)
            out += [c for t, c in chars.items() if t not in shown][: k - len(out)]
        return out


_model: CategoryModel | None = None


def get_model() -> CategoryModel:
    global _model
    if _model is None:
        s = get_settings()
        _model = CategoryModel(s.model_path, auto_rebuild=s.auto_rebuild_model)
    return _model


def build_text(merchant: str, items: list[str] | None = None) -> str:
    return " ".join([merchant or "", *(items or [])]).strip()


async def suggest(db, user_id, merchant: str, items: list[str] | None = None) -> dict:
    """Backward compatible: always has category / confidence / source / alternatives.
    New: status, abstained, threshold, explanation, model_version."""
    model = get_model()
    key = merchant_key(merchant)
    if key:
        ov = await db.merchant_overrides.find_one({"user_id": user_id, "merchant_key": key})
        if ov:
            return {"category": ov["category"], "confidence": 1.0, "source": "your correction", "alternatives": [],
                    "status": "override", "abstained": False, "threshold": model.threshold,
                    "explanation": [], "model_version": None}
    pred = model.predict(build_text(merchant, items))
    if pred is None:
        return {"category": UNCATEGORISED, "confidence": 0.0,
                "source": "unavailable" if not model.ready else "model",
                "alternatives": [], "status": "unavailable" if not model.ready else "low_confidence",
                "abstained": True, "threshold": model.threshold, "explanation": [],
                "model_version": (model.bundle or {}).get("version"),
                "detail": model.error if not model.ready else "Nothing to classify yet."}
    order = np.argsort(-pred["probs"])[:3]
    alternatives = [{"category": MODEL_CATEGORIES[i], "p": round(float(pred["probs"][i]), 3)} for i in order]
    abstain = pred["p"] < model.threshold
    return {
        "category": pred["top"],  # best guess, even when abstaining (the UI shows it as a hint only)
        "confidence": round(pred["p"], 3),
        "source": "model",
        "alternatives": alternatives,
        "status": "low_confidence" if abstain else "confident",
        "abstained": abstain,
        "threshold": model.threshold,
        "explanation": pred["explanation"],
        "model_version": model.bundle.get("version") if model.bundle else None,
    }


def resolved_category(s: dict) -> str:
    """What to store when the client didn't choose: the suggestion, or Uncategorised if we abstained."""
    return UNCATEGORISED if s.get("abstained") else s["category"]


async def record_correction(db, user_id, merchant: str, items: list[str], category: str, suggested: str | None) -> None:
    """User picked a category different from the suggestion: remember it for this merchant and keep
    the example so an admin retrain can fold it into the global model."""
    if category not in MODEL_CATEGORIES:
        return
    key = merchant_key(merchant)
    now = datetime.now(timezone.utc)
    if key:
        await db.merchant_overrides.update_one(
            {"user_id": user_id, "merchant_key": key},
            {"$set": {"category": category, "merchant": merchant, "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    await db.category_feedback.insert_one({
        "user_id": user_id, "text": build_text(merchant, items), "merchant": merchant,
        "category": category, "suggested": suggested, "created_at": now,
    })


def retrain_with_feedback(feedback: list[dict]) -> dict:
    """Refit on the synthetic base set + user corrections (each repeated 5x). Keeps the calibration
    temperature and threshold of the evaluated model (the card says so). CPU-bound: call in a thread."""
    from ml.evaluate_classifier import save_production_model
    model = get_model()
    card = model.card or {}
    fb = [(f["text"], f["category"]) for f in feedback if f.get("text") and f.get("category") in MODEL_CATEGORIES]
    X = [t for t, _ in fb for _ in range(5)]
    y = [c for _, c in fb for _ in range(5)]
    evaluation = dict(card.get("evaluation") or {})
    evaluation["note"] = ("Metrics describe the evaluated model before user corrections were added; "
                          "the retrained model has not been re-evaluated.")
    kind = (model.bundle or {}).get("kind") or card.get("kind", "logreg")
    res = save_production_model(card.get("run_config") or {"seed": 7}, evaluation, kind,
                                (model.bundle or {}).get("temperature", 1.0), model.threshold,
                                extra_X=X, extra_y=y, feedback_rows=len(fb), path=model.path)
    model.load(auto_rebuild=False)
    return {"trained_on": model.bundle.get("trained_on") if model.bundle else None, "feedback_rows": len(fb),
            "kind": kind, "version": res["version"]}
