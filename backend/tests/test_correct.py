"""OCR-error correction (app/pipeline/correct.py): fix confusions, never invent digits or rename shops."""
import pytest

from app.pipeline.correct import correct_lines, correct_text
from app.pipeline.ocr import OcrLine
from app.pipeline.receipt import parse_lines


@pytest.mark.parametrize("raw,fixed", [
    ("T0TAL 1,2O4.5O", "TOTAL 1,204.50"),
    ("TOTA1: 45.OO", "TOTAL: 45.00"),
    ("GRAND T0TAL l2.50", "GRAND TOTAL 12.50"),
    ("SUBT0TAL 12 . 50", "SUBTOTAL 12.50"),
    ("CGS7 @9% 4S.00", "CGST @9% 45.00"),
    ("Date: 1O/O3/2O18", "Date: 10/03/2018"),
    ("TOTAI 3.00", "TOTAL 3.00"),
    ("Item 1O0 pcs", "Item 100 pcs"),
])
def test_repairs(raw, fixed):
    assert correct_text(raw)[0] == fixed


@pytest.mark.parametrize("text", [
    "500g Sugar 2S",            # units are not digits
    "Grano Bakery",             # a shop name one letter from GRAND stays
    "INV12345 Total 10.00",     # bill numbers untouched
    "Tel 03-12345678",
    "SALES TAX 6% 1.20",
    "THANK YOU! VISIT AGAIN",
])
def test_leaves_correct_text_alone(text):
    assert correct_text(text) == (text, [])


def test_change_log_and_parse_effect():
    lines = [OcrLine("BIG SHOP", 90), OcrLine("Date: 12/O3/2O24", 80), OcrLine("T0TAL 1,2O4.5O", 70)]
    fixed, log = correct_lines(lines)
    assert [c["kind"] for c in log] == ["number", "keyword", "number"]
    assert {c["line"] for c in log} == {1, 2}
    assert lines[2].text == "T0TAL 1,2O4.5O"  # originals untouched
    out = parse_lines(lines)
    assert out["fields"]["total"]["value"] == 1204.5
    assert out["fields"]["date"]["value"] == "2024-03-12"
    assert out["parser_version"] == "1.3" and len(out["corrections"]) == 3
    old = parse_lines(lines, correct_ocr=False)
    assert old["parser_version"] == "1.3-nocorrect" and old["corrections"] == []
    assert parse_lines(lines, version="1.2")["parser_version"] == "1.2"
