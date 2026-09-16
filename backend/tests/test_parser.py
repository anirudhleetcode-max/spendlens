from datetime import date

import pytest

from app.pipeline.ocr import OcrLine
from app.pipeline.extract import match_known_merchant
from app.pipeline.normalise import amounts_in, find_dates
from app.pipeline.receipt import parse_lines as parse_receipt


def L(*texts):
    return [OcrLine(t, 92.0) for t in texts]


@pytest.mark.parametrize("text,expected", [
    ("Date: 16/09/2026", date(2026, 9, 16)),
    ("Dt: 16-09-26", date(2026, 9, 16)),
    ("Bill Dt: 05.08.2026", date(2026, 8, 5)),
    ("2026-07-01 18:40", date(2026, 7, 1)),
    ("Date 16-Sep-2026", date(2026, 9, 16)),
    ("16 Sept 2026", date(2026, 9, 16)),
    ("Sep 3, 2026", date(2026, 9, 3)),
    ("09/25/2025", date(2025, 9, 25)),  # US order only when day-first is impossible
])
def test_date_formats(text, expected):
    assert find_dates(text)[0] == expected


def test_rejects_impossible_and_future_dates():
    assert find_dates("32/13/2026") == []
    assert find_dates("Date: 01/01/2099") == []


def test_amounts_handle_ocr_quirks():
    assert amounts_in("Sub Total 1,375.00") == [1375.0]
    assert amounts_in("Sub Total 473,00") == [473.0]
    assert amounts_in("GRAND TOTAL Rs .497.00") == [497.0]
    assert amounts_in("CGST @2.5% 11.82") == [11.82]
    assert amounts_in("NET AMOUNT Rs.1,2O4.00") == [1204.0]  # letter O inside a number


def test_known_merchant_fuzzy():
    assert match_known_merchant("DMART")[0] == "DMart"
    assert match_known_merchant("APOLL0 PHARMACY")[0] == "Apollo Pharmacy"
    assert match_known_merchant("TAX INVOICE") is None


def test_total_prefers_grand_total_over_subtotal_and_tax():
    lines = L("RELIANCE FRESH", "Date: 02/09/2026", "Item Qty Rate Amount",
              "ONION 2 30.00 60.00", "PANEER 200G 1 92.00 92.00",
              "Total Qty: 3", "Sub Total 152.00", "CGST @2.5% 3.80", "SGST @2.5% 3.80",
              "Round Off +0.40", "GRAND TOTAL Rs.160.00", "You Saved Rs.12.00", "Payment: UPI")
    out = parse_receipt(lines)
    f = out["fields"]
    assert f["merchant"]["value"] == "Reliance Fresh"
    assert f["date"]["value"] == "2026-09-02"
    assert f["total"]["value"] == 160.0 and f["total"]["confidence"] >= 0.9
    assert f["tax"]["value"] == 7.6
    assert f["payment_mode"]["value"] == "UPI"
    assert [(i["name"], i["qty"], i["price"]) for i in out["items"]] == [("Onion", 2, 60.0), ("Paneer 200G", 1, 92.0)]


def test_total_repaired_by_receipt_arithmetic():
    # thermal "0" misread as "6": 540.06 does not add up, 540.00 does
    lines = L("MORE SUPERMARKET", "Sub Total 514.00", "CGST @2.5% 12.85", "SGST @2.5% 12.85",
              "Round Off +0.30", "NET AMOUNT Rs.540.06")
    f = parse_receipt(lines)["fields"]["total"]
    assert f["value"] == 540.0
    assert f["confidence"] < 0.8  # still flagged for the user to check


def test_total_fallback_to_largest_amount_is_low_confidence():
    lines = L("Corner Tea Stall", "Tea 2 20.00", "Samosa 3 45.00", "65.00")
    f = parse_receipt(lines)["fields"]["total"]
    assert f["value"] == 65.0 and f["confidence"] < 0.5


def test_unknown_merchant_uses_header_line():
    lines = L("SRI KRISHNA SWEETS", "12, GANDHI ROAD, MADURAI 625001", "GSTIN: 33ABCDE1234F1Z5",
              "Date: 01/09/2026", "TOTAL 240.00")
    f = parse_receipt(lines)["fields"]
    assert f["merchant"]["value"] == "Sri Krishna Sweets"
    assert f["merchant"]["confidence"] < 0.7  # not a known merchant -> flagged
    assert f["total"]["value"] == 240.0


def test_fuel_receipt():
    lines = L("INDIAN OIL", "Dt: 13/08/2026", "Product: PETROL", "Rate/Ltr: 101.80", "Volume(L): 7.37",
              "SALE AMOUNT: Rs. 750.00", "Payment Mode: CARD: VISA XXXX4821")
    out = parse_receipt(lines)
    assert out["fields"]["total"]["value"] == 750.0
    assert out["fields"]["payment_mode"]["value"] == "Card"
    assert out["items"][0]["name"] == "Petrol" and out["items"][0]["qty"] == 7.37


def test_item_row_with_ocr_punctuation():
    from app.pipeline.extract import extract_items as parse_items
    items = parse_items(L("Item Qty Rate Amount", "AMUL TAAZA 1L 3) 68.00 204.00", "EGGS 6PC 1 48.00 48.00",
                          "PARLE G 800G 2 x 90.00 180.00", "Sub Total 432.00"))
    assert [(i["name"], i["qty"], i["price"]) for i in items] == [
        ("Amul Taaza 1L", 3, 204.0), ("Eggs 6PC", 1, 48.0), ("Parle G 800G", 2, 180.0)]


def test_checks_explain_why_a_total_is_flagged():
    out = parse_receipt(L("CAFE X", "Sub Total 100.00", "CGST @2.5% 2.50", "SGST @2.5% 2.50", "TOTAL 150.00"))
    c = {x["id"]: x for x in out["checks"]}
    assert c["total_arithmetic"]["status"] == "fail"
    assert "₹150.00 ≠ subtotal ₹100.00 + tax ₹5.00 = ₹105.00" in c["total_arithmetic"]["message"]
    assert out["fields"]["total"]["confidence"] <= 0.6


def test_checks_pass_repair_fallback_and_missing():
    ok = parse_receipt(L("DMART", "Date: 01/09/2026", "Sub Total 100.00", "CGST 2.50", "SGST 2.50",
                         "GRAND TOTAL 105.00"))
    assert {x["id"]: x["status"] for x in ok["checks"]}["total_arithmetic"] == "pass"
    repaired = parse_receipt(L("MORE", "Sub Total 514.00", "CGST 12.85", "SGST 12.85", "Round Off +0.30",
                               "NET AMOUNT 540.06"))
    rc = {x["id"]: x for x in repaired["checks"]}["total_arithmetic"]
    assert rc["status"] == "warn" and "Corrected to ₹540.00" in rc["message"]
    assert repaired["fields"]["total"]["source"].endswith("digit-repair")
    fb = parse_receipt(L("Tea Stall", "Tea 2 20.00", "65.00"))
    ids = {x["id"] for x in fb["checks"]}
    assert {"total_source", "date_missing", "merchant_unknown"} <= ids
    none = parse_receipt(L("hello"))
    assert "total_missing" in {x["id"] for x in none["checks"]}


def test_field_evidence_points_at_source_line():
    lines = L("RELIANCE FRESH", "Date: 02/09/2026", "GRAND TOTAL Rs.160.00")
    f = parse_receipt(lines)["fields"]
    assert f["merchant"]["line"] == 0 and f["merchant"]["source"] == "lexicon"
    assert f["date"]["line"] == 1 and f["total"]["line"] == 2
    assert f["total"]["source"] == "keyword:grand total"


def test_tax_inclusive_total_line_is_a_total_candidate():
    lines = L("SOME TRADING SDN BHD", "Date: 12/03/2018", "Item 1 22.44", "SUBTOTAL 22.44",
              "TOTAL (GST INCL) 22.45", "GST Summary Amount Tax", "SR 21.17 1.27", "CASH 50.00")
    new = parse_receipt(lines)["fields"]["total"]
    assert new["value"] == 22.45 and new["source"].startswith("keyword:")
    old = parse_receipt(lines, legacy_total_rule=True)
    assert old["fields"]["total"]["source"].startswith("fallback")  # 1.1 skipped the line and guessed 50.00
    assert old["parser_version"] == "1.1"
    # a GST summary line is still not a total
    assert parse_receipt(L("X", "Total GST 1.27", "NET AMOUNT 22.45"))["fields"]["total"]["value"] == 22.45
