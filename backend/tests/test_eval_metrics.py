"""Label normalisation used by the real-data evaluation (experiments/receipts_eval.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.receipts_eval import alnum, label_date, label_total, norm_text, total_digits  # noqa: E402


def test_label_dates():
    assert label_date("15/01/2019") == "2019-01-15"
    assert label_date("25-03-2018") == "2018-03-25"
    assert label_date("12 MAR 2018") == "2018-03-12"
    assert label_date("") is None


def test_totals():
    assert label_total("193.00") == 193.0
    assert label_total("RM28.20") == 28.2
    assert label_total("1,234.50") == 1234.5
    assert total_digits("60.000") == "60000"
    assert total_digits(60000.0) == "60000"
    assert total_digits("193.00") == total_digits(193.0) == "193"


def test_text_normalisation():
    assert norm_text("  OJC   Marketing ") == "ojc marketing"
    assert alnum("GARDENIA BAKERIES (KL) SDN BHD") == "gardeniabakeriesklsdnbhd"
