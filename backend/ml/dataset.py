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


def make_sample_kind(merchant: str, vocab: list[str], rng: random.Random) -> tuple[str, str]:
    """One training/eval text and its kind: merchant_only | items_only | merchant_items."""
    mode = rng.random()
    if mode < 0.25:  # manual entry: merchant only
        text, kind = merchant, "merchant_only"
    elif mode < 0.35:  # items only (merchant header unreadable)
        text, kind = " ".join(rng.sample(vocab, k=min(len(vocab), rng.randint(2, 5)))), "items_only"
    else:
        text, kind = merchant + " " + " ".join(rng.sample(vocab, k=min(len(vocab), rng.randint(1, 6)))), "merchant_items"
    if rng.random() < 0.35:
        text = _ocr_noise(text, rng, p=0.08)
    return text, kind


def make_sample(merchant: str, vocab: list[str], rng: random.Random) -> str:
    return make_sample_kind(merchant, vocab, rng)[0]


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


def build_splits(seed: int = 7, per_merchant: int = 30, holdout_items: bool = True,
                 test_frac: float = 0.25, val_frac: float = 0.2) -> dict[str, dict]:
    """Train / validation / test with *merchants* disjoint across splits and, when holdout_items is
    True, *item words* disjoint too (each category's item list is split 60/20/20). This is the strict
    setting used for all reported classifier numbers: nothing the model sees at test time was seen in
    training, apart from generic sub-word pieces.

    Returns {"train"|"val"|"test": {"X": [...], "y": [...], "kind": [...], "merchant": [...]}}."""
    rng = random.Random(seed)
    splits = {k: {"X": [], "y": [], "kind": [], "merchant": []} for k in ("train", "val", "test")}
    for cat, (merchants, vocab) in DATA.items():
        ms = merchants[:]
        rng.shuffle(ms)
        n_te = max(3, round(len(ms) * test_frac))
        n_va = max(3, round(len(ms) * val_frac))
        by_split_m = {"test": ms[:n_te], "val": ms[n_te:n_te + n_va], "train": ms[n_te + n_va:]}
        vs = vocab[:]
        rng.shuffle(vs)
        if holdout_items:
            a, b = round(len(vs) * 0.6), round(len(vs) * 0.8)
            by_split_v = {"train": vs[:a], "val": vs[a:b], "test": vs[b:]}
        else:
            by_split_v = {k: vs for k in splits}
        for name, mlist in by_split_m.items():
            reps = per_merchant if name == "train" else per_merchant // 2
            for m in mlist:
                for _ in range(reps):
                    text, kind = make_sample_kind(m, by_split_v[name], rng)
                    sp = splits[name]
                    sp["X"].append(text); sp["y"].append(cat); sp["kind"].append(kind); sp["merchant"].append(m)
    return splits


def build_full(seed: int = 7, per_merchant: int = 30) -> tuple[list[str], list[str]]:
    """All merchants, used for the final model after evaluation."""
    rng = random.Random(seed + 1)
    X, y = [], []
    for cat, (merchants, vocab) in DATA.items():
        for m in merchants:
            for _ in range(per_merchant):
                X.append(make_sample(m, vocab, rng)); y.append(cat)
    return X, y


def fingerprint(X: list[str], y: list[str]) -> str:
    """sha256 of the generated samples - the 'dataset version' recorded in model cards."""
    import hashlib
    h = hashlib.sha256()
    for a, b in zip(X, y):
        h.update(f"{b}\t{a}\n".encode())
    return h.hexdigest()


if __name__ == "__main__":
    sp = build_splits()
    print({k: len(v["X"]) for k, v in sp.items()})
    for x, y in list(zip(sp["train"]["X"], sp["train"]["y"]))[::500]:
        print(f"{y:18} | {x}")
