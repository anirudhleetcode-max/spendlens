"""Category suggestion = per-user merchant override (learned from corrections) -> ML model -> 'Other'."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import joblib

from ..categories import CATEGORIES
from ..config import get_settings
from ..utils import merchant_key

log = logging.getLogger(__name__)


class CategoryModel:
    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.bundle: dict | None = None
        self.load()

    def load(self) -> None:
        import sklearn
        bundle = None
        if self.path.exists():
            try:
                bundle = joblib.load(self.path)
            except Exception as e:  # pickle from an incompatible scikit-learn
                log.warning("could not load category model (%s)", e)
        if bundle is None or bundle.get("sklearn") != sklearn.__version__:
            # pickles are tied to the scikit-learn version: rebuild locally (about 10 s) instead of failing
            log.warning("training category model for scikit-learn %s ...", sklearn.__version__)
            from ml import dataset
            from ml.train_classifier import train_final
            X, y = dataset.build_full()
            bundle = {"model": train_final(X, y, "logreg"), "kind": "logreg", "trained_on": len(X),
                      "feedback_rows": 0, "sklearn": sklearn.__version__}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(bundle, self.path, compress=3)
        with self._lock:
            self.bundle = bundle
        log.info("category model loaded (%s)", bundle.get("kind"))

    @property
    def ready(self) -> bool:
        return self.bundle is not None

    def predict(self, text: str) -> tuple[str, float, list[dict]]:
        if not self.ready or not text.strip():
            return "Other", 0.0, []
        model = self.bundle["model"]
        proba = model.predict_proba([text])[0]
        classes = list(model.classes_)
        ranked = sorted(zip(classes, proba), key=lambda p: -p[1])
        top = [{"category": c, "p": round(float(p), 3)} for c, p in ranked[:3]]
        return ranked[0][0], float(ranked[0][1]), top


_model: CategoryModel | None = None


def get_model() -> CategoryModel:
    global _model
    if _model is None:
        _model = CategoryModel(get_settings().model_path)
    return _model


def build_text(merchant: str, items: list[str] | None = None) -> str:
    return " ".join([merchant or "", *(items or [])]).strip()


async def suggest(db, user_id, merchant: str, items: list[str] | None = None) -> dict:
    key = merchant_key(merchant)
    if key:
        ov = await db.merchant_overrides.find_one({"user_id": user_id, "merchant_key": key})
        if ov:
            return {"category": ov["category"], "confidence": 1.0, "source": "your correction", "alternatives": []}
    cat, p, top = get_model().predict(build_text(merchant, items))
    return {"category": cat, "confidence": round(p, 3), "source": "model", "alternatives": top}


async def record_correction(db, user_id, merchant: str, items: list[str], category: str, suggested: str | None) -> None:
    """User picked a category (different from the suggestion): remember it for this merchant and keep
    the example so `retrain` can fold it into the global model."""
    if category not in CATEGORIES:
        return
    key = merchant_key(merchant)
    now = datetime.now(timezone.utc)
    if key:
        await db.merchant_overrides.update_one(
            {"user_id": user_id, "merchant_key": key},
            {"$set": {"category": category, "merchant": merchant, "updated_at": now}},
            upsert=True,
        )
    await db.category_feedback.insert_one({
        "user_id": user_id, "text": build_text(merchant, items), "merchant": merchant,
        "category": category, "suggested": suggested, "created_at": now,
    })


def retrain_with_feedback(feedback: list[dict]) -> dict:
    """Refit on the synthetic base set + user corrections (each correction is up-weighted by repetition).
    CPU-bound: call through a thread."""
    from ml import dataset
    from ml.train_classifier import MODEL, train_final

    X, y = dataset.build_full()
    fb = [(f["text"], f["category"]) for f in feedback if f.get("text") and f.get("category") in CATEGORIES]
    for text, cat in fb:
        X.extend([text] * 5)
        y.extend([cat] * 5)
    model = get_model()
    kind = model.bundle.get("kind", "logreg") if model.bundle else "logreg"
    final = train_final(X, y, "logreg" if kind == "logreg" else "cnb")
    import sklearn
    bundle = {"model": final, "kind": kind, "trained_on": len(X), "feedback_rows": len(fb), "sklearn": sklearn.__version__,
              "retrained_at": datetime.now(timezone.utc).isoformat()}
    tmp = Path(str(MODEL) + ".tmp")
    joblib.dump(bundle, tmp, compress=3)
    tmp.replace(model.path if model.path else MODEL)
    model.load()
    return {"trained_on": len(X), "feedback_rows": len(fb), "kind": kind}
