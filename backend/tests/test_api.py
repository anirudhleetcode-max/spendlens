import io
from datetime import date, timedelta

import pytest
from PIL import Image

from app.pipeline.ocr import tesseract_version
from app.utils import current_month
from ml.receipts_synth import generate

TODAY = date.today()


def expense(client, headers, **kw):
    body = {"merchant": "Chaayos", "amount": 240, "date": TODAY.isoformat(), "payment_mode": "UPI"} | kw
    r = client.post("/api/expenses", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_reports_ocr(client):
    body = client.get("/api/health").json()
    assert body["db"] == "connected"
    assert set(body["ocr"]) >= {"available", "version"}
    assert body["classifier"] is True
    assert body["model"]["status"] == "ready" and body["status"] in ("ok", "degraded")


def test_requires_auth(client):
    assert client.get("/api/expenses").status_code == 401
    r = client.post("/api/receipts/scan", files={"file": ("r.jpg", b"x", "image/jpeg")})
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated", "status": 401}


@pytest.mark.skipif(tesseract_version() is None, reason="Tesseract not installed")
def test_scan_receipt_end_to_end(client, new_user):
    img, truth = generate(1, seed=3)[0]
    r = client.post("/api/receipts/scan", files={"file": ("bill.jpg", img, "image/jpeg")}, headers=new_user)
    assert r.status_code == 201, r.text
    body = r.json()
    f = body["fields"]
    assert body["ocr_available"] is True
    assert f["merchant"]["value"] == truth.merchant
    assert f["date"]["value"] == truth.date
    assert abs(f["total"]["value"] - truth.total) < 0.01
    assert body["category"]["category"] == truth.category
    assert body["stored_bytes"] <= 1_000_000
    assert len(body["items"]) >= 1

    # image is served back only to its owner
    img_url = f"/api/receipts/{body['receipt_id']}/image"
    got = client.get(img_url, headers=new_user)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    other = client.post("/api/auth/register", json={"name": "O", "email": "other-scan@example.com",
                                                    "password": "secret123"}).json()["token"]
    assert client.get(img_url, headers={"Authorization": f"Bearer {other}"}).status_code == 404

    # save with a corrected category -> override is learned for this merchant
    saved = expense(client, new_user, merchant=f["merchant"]["value"], amount=f["total"]["value"],
                    date=f["date"]["value"], category="Other", suggested_category=body["category"]["category"],
                    receipt_id=body["receipt_id"], items=[{"name": i["name"], "qty": i["qty"], "price": i["price"]}
                                                          for i in body["items"]])
    assert saved["source"] == "scan" and saved["category"] == "Other"
    again = client.post("/api/categories/suggest", json={"merchant": truth.merchant}, headers=new_user).json()
    assert {k: again[k] for k in ("category", "confidence", "source", "alternatives", "status")} == {
        "category": "Other", "confidence": 1.0, "source": "your correction", "alternatives": [], "status": "override"}

    # deleting the expense removes the image
    assert client.delete(f"/api/expenses/{saved['id']}", headers=new_user).status_code == 204
    assert client.get(img_url, headers=new_user).status_code == 404


def test_scan_without_tesseract_still_stores_image(client, new_user, monkeypatch):
    from app.routers import receipts
    monkeypatch.setattr(receipts, "ocr_status", lambda: {"available": False, "version": None, "cmd": None})
    img, _ = generate(1, seed=9)[0]
    r = client.post("/api/receipts/scan", files={"file": ("bill.jpg", img, "image/jpeg")}, headers=new_user)
    assert r.status_code == 201
    body = r.json()
    assert body["ocr_available"] is False
    assert body["fields"]["total"]["value"] is None
    assert client.get(f"/api/receipts/{body['receipt_id']}/image", headers=new_user).status_code == 200


def test_scan_validation(client, auth_headers):
    r = client.post("/api/receipts/scan", files={"file": ("a.pdf", b"%PDF", "application/pdf")}, headers=auth_headers)
    assert r.status_code == 415
    # content-type says JPEG, bytes say otherwise: rejected by magic-byte sniffing
    r = client.post("/api/receipts/scan", files={"file": ("a.jpg", b"garbage", "image/jpeg")}, headers=auth_headers)
    assert r.status_code == 415
    # right magic bytes, broken body: Pillow can't parse it
    r = client.post("/api/receipts/scan", files={"file": ("a.jpg", b"\xff\xd8\xff\xe0" + b"0" * 200, "image/jpeg")},
                    headers=auth_headers)
    assert r.status_code == 422
    big = io.BytesIO()
    Image.effect_noise((4200, 4200), 90).convert("RGB").save(big, "PNG")
    assert big.tell() > 8 * 1024 * 1024
    r = client.post("/api/receipts/scan", files={"file": ("big.png", big.getvalue(), "image/png")}, headers=auth_headers)
    assert r.status_code == 413


def test_manual_expense_gets_model_category(client, new_user):
    e = expense(client, new_user, merchant="HP Petrol Pump", amount=500, items=[{"name": "petrol"}])
    assert e["category"] == "Transport & Fuel" and e["source"] == "manual"


def test_validation_errors_are_consistent(client, auth_headers):
    r = client.post("/api/expenses", json={"merchant": "", "amount": -5, "date": "nope"}, headers=auth_headers)
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == 422 and isinstance(body["detail"], list) and body["detail"][0]["msg"]
    r = client.post("/api/expenses", json={"merchant": "X", "amount": 5, "date": "2026-01-01", "category": "Food"},
                    headers=auth_headers)
    assert r.status_code == 422
    assert client.get("/api/expenses/not-an-id", headers=auth_headers).status_code == 404


def test_list_filter_search_paginate(client, new_user):
    last_month = (TODAY.replace(day=1) - timedelta(days=3)).isoformat()
    for i in range(7):
        expense(client, new_user, merchant=f"Swiggy {i}", amount=100 + i, category="Food & Dining")
    expense(client, new_user, merchant="DMart", amount=900, category="Groceries",
            items=[{"name": "Toor Dal", "qty": 1, "price": 142}])
    expense(client, new_user, merchant="Old Cafe", amount=50, category="Food & Dining", date=last_month)

    month = current_month()
    r = client.get(f"/api/expenses?month={month}&limit=5", headers=new_user).json()
    assert r["total"] == 8 and r["pages"] == 2 and len(r["items"]) == 5
    assert r["sum"] == pytest.approx(sum(100 + i for i in range(7)) + 900)
    p2 = client.get(f"/api/expenses?month={month}&limit=5&page=2", headers=new_user).json()
    assert len(p2["items"]) == 3
    assert not {e["id"] for e in r["items"]} & {e["id"] for e in p2["items"]}

    groc = client.get(f"/api/expenses?month={month}&category=Groceries", headers=new_user).json()
    assert [e["merchant"] for e in groc["items"]] == ["DMart"]
    by_item = client.get("/api/expenses?q=toor", headers=new_user).json()
    assert by_item["total"] == 1
    assert client.get("/api/expenses?q=.*", headers=new_user).json()["total"] == 0  # regex is escaped
    assert client.get("/api/expenses", headers=new_user).json()["total"] == 9
    assert client.get("/api/expenses?month=2026-13x", headers=new_user).status_code == 422


def test_update_category_records_override_and_isolation(client, new_user, auth_headers):
    e = expense(client, new_user, merchant="Zudio Koramangala", amount=799)
    r = client.patch(f"/api/expenses/{e['id']}", json={"category": "Travel", "amount": 810.456}, headers=new_user)
    assert r.status_code == 200
    assert r.json()["category"] == "Travel" and r.json()["amount"] == 810.46
    nxt = expense(client, new_user, merchant="ZUDIO  koramangala", amount=300)
    assert nxt["category"] == "Travel"  # override applied before the model
    overrides = client.get("/api/categories/overrides", headers=new_user).json()
    assert overrides[0]["category"] == "Travel"
    # another user can neither see nor edit it, and is not affected by the override
    assert client.patch(f"/api/expenses/{e['id']}", json={"amount": 1}, headers=auth_headers).status_code == 404
    assert client.delete(f"/api/expenses/{e['id']}", headers=auth_headers).status_code == 404
    s = client.post("/api/categories/suggest", json={"merchant": "Zudio Koramangala"}, headers=auth_headers).json()
    assert s["source"] == "model"


def test_budgets_and_projection(client, new_user):
    assert client.put("/api/budgets", json={"category": "Groceries", "amount": 1000}, headers=new_user).status_code == 200
    assert client.put("/api/budgets", json={"category": "Nope", "amount": 1}, headers=new_user).status_code == 422
    client.put("/api/budgets", json={"category": "Shopping", "amount": 5000}, headers=new_user)
    expense(client, new_user, merchant="DMart", amount=1200, category="Groceries",
            date=TODAY.replace(day=1).isoformat())
    b = client.get("/api/budgets", headers=new_user).json()
    rows = {x["category"]: x for x in b["budgets"]}
    assert rows["Groceries"]["status"] == "over" and rows["Groceries"]["pct"] == 120.0
    assert rows["Shopping"]["status"] == "ok" and rows["Shopping"]["spent"] == 0
    # budget is under but the pace says it won't be: 400 spent on day d projects to 400*dim/d
    client.put("/api/budgets", json={"category": "Groceries", "amount": 1300}, headers=new_user)
    g = {x["category"]: x for x in client.get("/api/budgets", headers=new_user).json()["budgets"]}["Groceries"]
    expected = "at_risk" if g["projected"] > 1300 else "ok"
    assert g["status"] == expected
    # a past month is complete: projected == spent
    past = client.get("/api/budgets?month=2020-01", headers=new_user).json()
    assert past["days_elapsed"] == past["days_in_month"] == 31
    assert client.delete("/api/budgets/Shopping", headers=new_user).status_code == 204
    assert client.delete("/api/budgets/Shopping", headers=new_user).status_code == 404


def test_overview_and_anomalies(client, new_user):
    start = TODAY.replace(day=1)
    for i, amt in enumerate([300, 320, 280, 350, 310, 290, 305]):
        expense(client, new_user, merchant="Zomato", amount=amt, category="Food & Dining",
                date=(start - timedelta(days=i + 1)).isoformat())
    big = expense(client, new_user, merchant="Barbeque Nation", amount=2100, category="Food & Dining",
                  date=start.isoformat())
    expense(client, new_user, merchant="Uber", amount=200, category="Transport & Fuel", date=start.isoformat())
    o = client.get("/api/insights/overview", headers=new_user).json()
    assert o["total"] == 2300 and o["count"] == 2
    assert o["previous_total"] == 2155
    # month in progress: compared with the same days of last month (the seeded rows are at its very end)
    assert o["compared_days"] == TODAY.day
    last_days = sum(amt for i, amt in enumerate([300, 320, 280, 350, 310, 290, 305])
                    if (start - timedelta(days=i + 1)).day <= TODAY.day)
    assert o["previous_to_date"] == last_days
    assert o["change_pct"] == (round(100 * (2300 - last_days) / last_days, 1) if last_days else None)
    past = client.get(f"/api/insights/overview?month={(start - timedelta(days=1)).strftime('%Y-%m')}",
                      headers=new_user).json()
    assert past["compared_days"] is None and past["total"] == 2155
    assert [c["category"] for c in o["by_category"]] == ["Food & Dining", "Transport & Fuel"]
    assert o["daily"][0]["amount"] == 2300 and o["daily"][-1]["cumulative"] == 2300
    assert o["top_merchants"][0]["merchant"] == "Barbeque Nation"
    assert [a["id"] for a in o["anomalies"]] == [big["id"]]
    assert "your usual Food & Dining spend" in o["anomalies"][0]["anomaly"]["reason"]
    assert "robust z" in o["anomalies"][0]["anomaly"]["detail"]
    listed = client.get("/api/expenses", headers=new_user).json()["items"]
    assert next(e for e in listed if e["id"] == big["id"])["anomaly"]["ratio"] >= 6


def test_export_csv(client, new_user):
    expense(client, new_user, merchant="Café Madras, Matunga", amount=1234.5, category="Food & Dining",
            items=[{"name": "Dosa", "qty": 2, "price": 200}])
    r = client.get(f"/api/expenses/export?month={current_month()}", headers=new_user)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "spendlens-" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("Date,Merchant,Category")
    assert '"Café Madras, Matunga",Food & Dining,1234.50' in lines[1]
    assert "Dosa x2" in lines[1]


def test_retrain_is_admin_only_and_folds_in_feedback(client, new_user, monkeypatch):
    e = expense(client, new_user, merchant="Kumar Tiffin Centre", amount=90, category="Food & Dining",
                suggested_category="Other")
    assert e["category"] == "Food & Dining"
    r = client.post("/api/categories/retrain", headers=new_user)
    assert r.status_code == 403
    me = client.get("/api/auth/me", headers=new_user).json()
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "admin_emails", me["email"])
    r = client.post("/api/categories/retrain", headers=new_user)
    assert r.status_code == 200, r.text
    assert r.json()["feedback_rows"] >= 1
    card = client.get("/api/model").json()["category_model"]["card"]
    assert card["training_data"]["synthetic"] is True
    assert card["training_data"]["user_corrections"] >= 1
    assert "not been re-evaluated" in card["evaluation"]["note"]
