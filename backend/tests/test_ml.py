import pytest

from app.services import anomaly
from app.services.classifier import get_model


@pytest.mark.parametrize("text,cat", [
    ("DMart toor dal amul butter", "Groceries"),
    ("Swiggy chicken biryani delivery charge", "Food & Dining"),
    ("HP Petrol Pump speed petrol", "Transport & Fuel"),
    ("Apollo Pharmacy dolo 650 tab", "Health"),
    ("PVR INOX movie ticket popcorn combo", "Entertainment"),
    ("IRCTC train ticket 3a berth", "Travel"),
    ("BESCOM electricity bill", "Bills & Utilities"),
    ("Sri Sai Medicals paracetamol strip", "Health"),  # unseen merchant, items carry it
])
def test_classifier_predictions(text, cat):
    out = get_model().predict(text)
    assert out["top"] == cat, (text, out)
    assert 0 < out["p"] <= 1
    assert abs(out["probs"].sum() - 1) < 1e-6


def test_classifier_handles_empty_text():
    assert get_model().predict("") is None
    assert get_model().predict("   ") is None


def test_robust_stats_ignore_single_outlier():
    amounts = [300, 320, 280, 350, 310, 290, 5000]
    med, mad = anomaly.robust_stats(amounts)
    assert med == 310 and mad == 20
    flag, z, ratio = anomaly.is_anomaly(1200, (med, mad))
    assert flag and ratio > 3
    assert not anomaly.is_anomaly(340, (med, mad))[0]


def test_robust_stats_needs_history_and_handles_zero_mad():
    assert anomaly.robust_stats([100, 200]) is None
    med, mad = anomaly.robust_stats([500] * 8)
    assert med == 500 and mad == 50  # fallback to 10% of median
    assert anomaly.is_anomaly(1500, (med, mad))[0]


def test_budget_projection():
    from app.routers.budgets import project
    assert project(3000, 10, 30) == 9000
    assert project(0, 0, 30) == 0


def test_anomaly_rule_boundaries():
    stats = (300.0, 20.0)  # median, MAD
    rule = anomaly.RULE
    # z exactly at the threshold is NOT flagged (strictly greater is required)
    x_at = 300 + rule.z_threshold * 20 / 0.6745
    assert not anomaly.is_anomaly(x_at, stats)[0]
    # far above in z but below 2x the median: not flagged
    assert not anomaly.is_anomaly(590, stats)[0]
    # exactly 2x the median and z > 3.5: flagged
    flag, z, ratio = anomaly.is_anomaly(600, stats)
    assert flag and ratio == 2.0 and z > rule.z_threshold
    # below-median outliers are never flagged (we only warn about unusually large spends)
    assert not anomaly.is_anomaly(10, stats)[0]


def test_anomaly_explanation_text():
    e = anomaly.explain("Health", 2890, (400.0, 80.0))
    assert e["reason"] == "7.2× your usual Health spend"
    assert "₹400" in e["detail"] and "robust z" in e["detail"]
    assert e["rule"]["min_history"] == 6


def test_calibration_helpers():
    import numpy as np
    from ml.calibration import brier, fit_temperature, pick_threshold, reliability, softmax
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 500)
    logits = rng.normal(0, 1, (500, 3))
    logits[np.arange(500), y] += 1.0
    over = logits * 4  # deliberately over-confident
    T = fit_temperature(over, y)
    assert T > 1.5  # temperature scaling softens it
    p_raw, p_cal = softmax(over), softmax(over / T)
    ece_raw, _ = reliability(p_raw.max(1), p_raw.argmax(1) == y)
    ece_cal, table = reliability(p_cal.max(1), p_cal.argmax(1) == y)
    assert ece_cal < ece_raw
    assert sum(r["n"] for r in table) == 500
    assert (p_raw.argmax(1) == p_cal.argmax(1)).all()  # accuracy unchanged
    assert 0 <= brier(p_cal, y) <= 2
    t, rows = pick_threshold(p_cal.max(1), p_cal.argmax(1) == y, 0.8)
    kept = [r for r in rows if r["threshold"] == t][0]
    assert kept["accuracy"] >= 0.8


def test_keyword_baseline():
    from ml.baselines import KeywordRules
    m = KeywordRules().fit(["a", "b", "b"], ["Groceries", "Health", "Health"])
    assert list(m.predict(["Sri Sai Medicals", "nothing here"])) == ["Health", "Health"]


def test_strict_split_is_disjoint():
    from ml.dataset import build_splits
    sp = build_splits(per_merchant=4)
    tr, te = set(sp["train"]["merchant"]), set(sp["test"]["merchant"])
    assert not tr & te and not set(sp["val"]["merchant"]) & te
