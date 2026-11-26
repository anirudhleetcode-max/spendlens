"""Preprocessing alternatives, image-quality measures, degradations and the new evaluation metrics."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pipeline.preprocess import (DENOISE_METHODS, THRESHOLD_METHODS, decode, denoise, image_quality,  # noqa: E402
                                     noise_sigma, preprocess, threshold)
from experiments.quality import CORRUPTIONS, degrade, spearman  # noqa: E402
from experiments.receipts_eval import cer, ocr_key, pctl, prf, wer  # noqa: E402
from ml.receipts_synth import generate  # noqa: E402


@pytest.fixture(scope="module")
def receipt():
    return generate(1, seed=11)[0][0]


@pytest.mark.parametrize("method", THRESHOLD_METHODS)
def test_threshold_methods_binary_text_dark(method, receipt):
    gray = cv2.cvtColor(decode(receipt), cv2.COLOR_BGR2GRAY)
    out = threshold(gray, method)
    assert out.shape == gray.shape and out.dtype == np.uint8
    if method != "none":
        assert set(np.unique(out)) <= {0, 255}
        assert 0.5 < (out == 255).mean() < 0.99  # mostly paper, some ink


@pytest.mark.parametrize("method", DENOISE_METHODS)
def test_denoise_reduces_noise(method):
    rng = np.random.default_rng(0)
    clean = np.full((200, 200), 180, np.uint8)
    noisy = np.clip(clean + rng.normal(0, 20, clean.shape), 0, 255).astype(np.uint8)
    out = denoise(noisy, method)
    assert out.shape == noisy.shape
    if method != "none":
        assert out.std() < noisy.std() * 0.8


def test_unknown_methods_rejected():
    with pytest.raises(ValueError):
        threshold(np.zeros((5, 5), np.uint8), "magic")
    with pytest.raises(ValueError):
        denoise(np.zeros((5, 5), np.uint8), "magic")


def test_preprocess_options(receipt):
    img = decode(receipt)
    a = preprocess(img)
    b = preprocess(img, denoise_method="none", threshold_method="otsu", deskew=False)
    assert b.skew == 0.0 and a.binary.shape[0] > 0 and b.binary.shape[0] > 0


def test_noise_sigma_estimate():
    rng = np.random.default_rng(1)
    flat = np.full((400, 400), 128.0)
    for s in (5, 15, 30):
        est = noise_sigma(np.clip(flat + rng.normal(0, s, flat.shape), 0, 255).astype(np.uint8))
        assert abs(est - s) < 0.2 * s + 1


def test_quality_flags_follow_degradation(receipt):
    clean = image_quality(decode(receipt))
    blurred = image_quality(decode(degrade(receipt, "gaussian_blur", 4.5)))
    dark = image_quality(decode(degrade(receipt, "dark", 0.22)))
    faded = image_quality(decode(degrade(receipt, "low_contrast", 0.15)))
    assert blurred["sharpness"] < clean["sharpness"] / 3
    assert "blurry" in [i["code"] for i in blurred["issues"]]
    assert "dark" in [i["code"] for i in dark["issues"]]
    assert faded["contrast"] < clean["contrast"] / 3
    assert "low_contrast" in [i["code"] for i in faded["issues"]]


@pytest.mark.parametrize("kind", list(CORRUPTIONS))
def test_every_corruption_decodes(kind, receipt):
    out = decode(degrade(receipt, kind, CORRUPTIONS[kind][1], seed=3))
    assert out.ndim == 3 and min(out.shape[:2]) > 50
    assert degrade(receipt, kind, CORRUPTIONS[kind][1], seed=3) == degrade(receipt, kind, CORRUPTIONS[kind][1], seed=3)


def test_wer_and_cer():
    assert wer("total 10.00", "total 10.00") == 0
    assert wer("totl 10.00", "total 10.00") == 0.5            # one substitution in two words
    assert wer("grand total 10.00", "total 10.00") == 0.5     # one insertion
    assert wer("", "a b c d") == 1.0
    assert cer("abcd", "abce") == 0.25


def test_precision_recall():
    rows = [{"filled": True, "exact": True, "conf": 0.9},
            {"filled": True, "exact": False, "conf": 0.4},
            {"filled": False, "exact": False, "conf": 0.0},
            {"filled": True, "exact": True, "conf": 0.5}]
    m = prf(rows)
    assert (m["precision"], m["recall"], m["tp"], m["fp"], m["fn"]) == (0.6667, 0.5, 2, 1, 2)
    auto = prf(rows, threshold=0.6)  # only the confident value is auto-accepted
    assert (auto["precision"], auto["recall"]) == (1.0, 0.25)


def test_percentile_and_spearman():
    assert pctl([5, 1, 3, 2, 4], 0.5) == 3
    assert pctl([], 0.5) is None
    assert spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == 1.0
    assert spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == -1.0


def test_ocr_cache_key_keeps_old_paths():
    assert ocr_key({"preprocess": True, "dual": True, "psm": 6}) == "pre1-dual1-psm6"
    assert ocr_key({"psm": 6, "threshold": "adaptive_gaussian"}) == "pre1-dual1-psm6"
    assert ocr_key({"psm": 4, "threshold": "otsu", "deskew": False}) == "pre1-dual1-psm4-thresholdotsu-deskew0"


def test_scan_checks_from_quality_and_corrections():
    from app.routers.receipts import quality_checks
    checks = quality_checks({"issues": [{"code": "blurry", "message": "blurred"}]},
                            [{"line": 3, "from": "T0TAL", "to": "TOTAL", "kind": "keyword"},
                             {"line": 3, "from": "1 . 50", "to": "1.50", "kind": "spacing"}])
    assert [c["id"] for c in checks] == ["photo_blurry", "ocr_corrections"]
    assert "T0TAL → TOTAL" in checks[1]["message"] and "Fixed 1 likely OCR misread:" in checks[1]["message"]
    assert quality_checks({"issues": []}, []) == []
