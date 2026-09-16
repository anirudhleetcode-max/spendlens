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
    got, p, top = get_model().predict(text)
    assert got == cat, (text, top)
    assert 0 < p <= 1


def test_classifier_handles_empty_text():
    assert get_model().predict("") == ("Other", 0.0, [])


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
