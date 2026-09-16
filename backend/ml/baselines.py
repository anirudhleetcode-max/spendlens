"""Baselines for the category classifier, evaluated on exactly the same split as the main model."""
from __future__ import annotations

import re

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin

# Hand-written, the way someone would write a first version without ML. Deliberately NOT generated
# from the training lexicon (that would leak the dataset into the "rules").
KEYWORDS: dict[str, list[str]] = {
    "Groceries": ["mart", "bazaar", "grocery", "kirana", "supermarket", "provision", "fresh", "dal", "atta",
                  "rice", "milk", "vegetable", "store"],
    "Food & Dining": ["restaurant", "cafe", "coffee", "pizza", "biryani", "dhaba", "hotel", "food", "kitchen",
                      "burger", "dosa", "thali", "naan", "tea", "chai", "sweets"],
    "Transport & Fuel": ["petrol", "diesel", "fuel", "oil", "pump", "cab", "taxi", "metro", "ride", "parking",
                         "toll", "fastag", "auto", "bus", "service station"],
    "Shopping": ["fashion", "shoes", "clothing", "electronics", "mobile", "shirt", "jeans", "watch", "digital",
                 "lifestyle", "mall"],
    "Health": ["pharmacy", "medical", "medicals", "chemist", "hospital", "clinic", "lab", "diagnostic", "health",
               "tablet", "dental", "gym"],
    "Bills & Utilities": ["electricity", "power", "broadband", "fiber", "recharge", "gas", "water", "bill",
                          "postpaid", "insurance", "rent", "maintenance"],
    "Entertainment": ["cinema", "movie", "cinemas", "theatre", "netflix", "music", "games", "gaming",
                      "subscription", "ticket", "concert"],
    "Travel": ["travel", "travels", "flight", "air", "railway", "train", "hotels", "trip", "tours", "booking",
               "stay", "resort"],
    "Education": ["school", "college", "university", "academy", "institute", "book", "books", "stationery",
                  "course", "tuition", "exam", "classes"],
    "Other": ["salon", "courier", "laundry", "tailor", "donation", "temple", "post", "repair"],
}


class KeywordRules(BaseEstimator, ClassifierMixin):
    """Count keyword hits per category; ties and no-hit texts fall back to the majority class."""

    def fit(self, X, y):
        vals, counts = np.unique(y, return_counts=True)
        self.classes_ = np.array(sorted(vals))
        self.majority_ = vals[np.argmax(counts)]
        self.patterns_ = {c: re.compile(r"\b(" + "|".join(map(re.escape, KEYWORDS.get(c, ["$^"]))) + r")\b", re.I)
                          for c in self.classes_}
        return self

    def _scores(self, x: str) -> np.ndarray:
        return np.array([len(self.patterns_[c].findall(x)) for c in self.classes_], dtype=float)

    def predict_proba(self, X):
        out = []
        for x in X:
            s = self._scores(x)
            if s.sum() == 0:
                p = (self.classes_ == self.majority_).astype(float)
            else:
                p = s / s.sum()
            out.append(p)
        return np.vstack(out)

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(1)]
