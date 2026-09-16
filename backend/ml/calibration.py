"""Probability calibration and confidence diagnostics.

Temperature scaling (Guo et al., 2017): divide the model's logits by one scalar T fitted on the
validation split by minimising negative log-likelihood. T > 1 softens over-confident probabilities,
T < 1 sharpens under-confident ones. The arg-max (the predicted class) never changes, so accuracy is
untouched - only the confidence numbers move.
"""
from __future__ import annotations

import numpy as np


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(probs: np.ndarray, y_idx: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(probs[np.arange(len(y_idx)), y_idx], 1e-12, 1))))


def fit_temperature(logits: np.ndarray, y_idx: np.ndarray) -> float:
    """1-D search over log T (golden-section on a coarse-to-fine grid; no scipy needed)."""
    grid = np.exp(np.linspace(np.log(0.05), np.log(20), 200))
    losses = [nll(softmax(logits / t), y_idx) for t in grid]
    best = grid[int(np.argmin(losses))]
    fine = np.exp(np.linspace(np.log(best / 1.1), np.log(best * 1.1), 100))
    losses = [nll(softmax(logits / t), y_idx) for t in fine]
    return float(fine[int(np.argmin(losses))])


def brier(probs: np.ndarray, y_idx: np.ndarray) -> float:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y_idx)), y_idx] = 1
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def reliability(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> tuple[float, list[dict]]:
    """Top-label expected calibration error and the per-bin table behind it."""
    edges = np.linspace(0, 1, bins + 1)
    table, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        n = int(m.sum())
        if n == 0:
            table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": 0, "mean_confidence": None, "accuracy": None})
            continue
        acc, cf = float(correct[m].mean()), float(conf[m].mean())
        ece += n / len(conf) * abs(acc - cf)
        table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": n, "mean_confidence": round(cf, 4), "accuracy": round(acc, 4)})
    return float(ece), table


def pick_threshold(conf: np.ndarray, correct: np.ndarray, target_accuracy: float) -> tuple[float, list[dict]]:
    """Smallest confidence threshold whose accepted predictions reach the target accuracy (on the
    validation split). Returns the threshold and the full risk-coverage table."""
    rows, chosen = [], None
    for t in np.round(np.arange(0.0, 0.96, 0.05), 2):
        keep = conf >= t
        cov = float(keep.mean())
        acc = float(correct[keep].mean()) if keep.any() else None
        rows.append({"threshold": float(t), "coverage": round(cov, 4), "accuracy": None if acc is None else round(acc, 4)})
        if chosen is None and acc is not None and acc >= target_accuracy:
            chosen = float(t)
    return (chosen if chosen is not None else 0.95), rows
