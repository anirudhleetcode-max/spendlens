"""Synthetic, India-first dataset for the expense category classifier.

Each sample is the text we have at prediction time: merchant name plus (optionally) a few line-item
names, the way they come out of a receipt. Merchants are split into train/test *by merchant*, so the
test score measures generalisation to shops the model has never seen, not memorisation.

    python -m ml.dataset          # prints a few rows and the split sizes
"""
from __future__ import annotations

import random

from app.pipeline.lexicon import DATA, known_merchants  # noqa: F401  (re-exported)


def _ocr_noise(text: str, rng: random.Random, p: float) -> str:
    """Imitate Tesseract slips: dropped / swapped characters and case changes."""
    swaps = {"o": "0", "l": "1", "i": "l", "s": "5", "e": "c", "a": "o", "b": "h", "m": "rn"}
    out = []
    for ch in text:
        r = rng.random()
        if r < p / 3:
            continue
        if r < 2 * p / 3 and ch.lower() in swaps:
            out.append(swaps[ch.lower()])
            continue
        out.append(ch)
    s = "".join(out)
    if rng.random() < 0.3:
        s = s.upper()
    return s


def make_sample(merchant: str, vocab: list[str], rng: random.Random) -> str:
    mode = rng.random()
    if mode < 0.25:  # manual entry: merchant only
        text = merchant
    elif mode < 0.35:  # items only (merchant header unreadable)
        text = " ".join(rng.sample(vocab, k=rng.randint(2, 5)))
    else:
        text = merchant + " " + " ".join(rng.sample(vocab, k=rng.randint(1, 6)))
    if rng.random() < 0.35:
        text = _ocr_noise(text, rng, p=0.08)
    return text


def split_merchants(seed: int = 7, test_frac: float = 0.25) -> tuple[dict, dict]:
    rng = random.Random(seed)
    train, test = {}, {}
    for cat, (merchants, _) in DATA.items():
        ms = merchants[:]
        rng.shuffle(ms)
        k = max(3, round(len(ms) * test_frac))
        test[cat], train[cat] = ms[:k], ms[k:]
    return train, test


def build(seed: int = 7, per_merchant: int = 30) -> tuple[list[str], list[str], list[str], list[str]]:
    """Returns X_train, y_train, X_test, y_test with merchants disjoint between the two."""
    rng = random.Random(seed)
    train_m, test_m = split_merchants(seed)
    X_tr, y_tr, X_te, y_te = [], [], [], []
    for cat, (_, vocab) in DATA.items():
        # items vocabulary is shared (items are generic); the merchant names are what is held out
        for m in train_m[cat]:
            for _ in range(per_merchant):
                X_tr.append(make_sample(m, vocab, rng)); y_tr.append(cat)
        for m in test_m[cat]:
            for _ in range(per_merchant // 2):
                X_te.append(make_sample(m, vocab, rng)); y_te.append(cat)
    return X_tr, y_tr, X_te, y_te


def build_full(seed: int = 7, per_merchant: int = 30) -> tuple[list[str], list[str]]:
    """All merchants, used for the final model after evaluation."""
    rng = random.Random(seed + 1)
    X, y = [], []
    for cat, (merchants, vocab) in DATA.items():
        for m in merchants:
            for _ in range(per_merchant):
                X.append(make_sample(m, vocab, rng)); y.append(cat)
    return X, y


if __name__ == "__main__":
    Xtr, ytr, Xte, yte = build()
    print(len(Xtr), "train /", len(Xte), "test")
    for x, y in list(zip(Xtr, ytr))[::400]:
        print(f"{y:18} | {x}")
