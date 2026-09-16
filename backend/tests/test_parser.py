from datetime import date

import pytest

from app.services.ocr import OcrLine
from app.services.parser import amounts_in, find_dates, match_known_merchant, parse_receipt


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
    from app.services.parser import parse_items
    items = parse_items(L("Item Qty Rate Amount", "AMUL TAAZA 1L 3) 68.00 204.00", "EGGS 6PC 1 48.00 48.00",
                          "PARLE G 800G 2 x 90.00 180.00", "Sub Total 432.00"))
    assert [(i["name"], i["qty"], i["price"]) for i in items] == [
        ("Amul Taaza 1L", 3, 204.0), ("Eggs 6PC", 1, 48.0), ("Parle G 800G", 2, 180.0)]
