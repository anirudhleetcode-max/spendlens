"""Robustness: bad uploads, degraded model, abstention, auth hardening, orphan cleanup."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app.config import InsecureSecretError, Settings, check_jwt_secret


def png(w, h, color=(255, 255, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def scan(client, headers, data, name="r.png", ctype="image/png"):
    return client.post("/api/receipts/scan", files={"file": (name, data, ctype)}, headers=headers)


def test_empty_upload(client, auth_headers):
    r = scan(client, auth_headers, b"")
    assert r.status_code == 422 and r.json()["detail"] == "The file is empty"


def test_decompression_bomb_is_refused(client, auth_headers):
    data = png(8000, 8000)  # 64 MP of white compresses to a few hundred KB
    assert len(data) < 1_000_000
    r = scan(client, auth_headers, data)
    assert r.status_code == 422 and "too large" in r.json()["detail"]


def test_wrong_declared_type_but_real_image_is_sniffed(client, new_user):
    r = scan(client, new_user, png(300, 400), name="photo.bin", ctype="application/octet-stream")
    assert r.status_code == 201


def test_non_image_content_type_rejected(client, auth_headers):
    r = scan(client, auth_headers, png(10, 10), name="x.png", ctype="text/html")
    assert r.status_code == 415


def test_blank_low_quality_image_gives_low_confidence_not_error(client, new_user):
    r = scan(client, new_user, png(120, 160, (200, 200, 200)))
    assert r.status_code == 201
    body = r.json()
    if body["ocr_available"]:
        assert body["fields"]["total"]["value"] is None
        assert any(c["id"] == "total_missing" for c in body["checks"])
        assert body["category"]["abstained"] is True


def test_webp_upload(client, new_user):
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(buf, "WEBP")
    assert scan(client, new_user, buf.getvalue(), "r.webp", "image/webp").status_code == 201


def test_discard_and_orphan_cleanup(client, new_user):
    from app.config import get_settings
    import pymongo
    r1 = scan(client, new_user, png(300, 400)).json()
    r2 = scan(client, new_user, png(300, 400)).json()
    # discard: only pending scans
    assert client.delete(f"/api/receipts/{r1['receipt_id']}", headers=new_user).status_code == 204
    assert client.get(f"/api/receipts/{r1['receipt_id']}/image", headers=new_user).status_code == 404
    # attach r3 to an expense, age r2 and r3, run cleanup: only r2 goes
    r3 = scan(client, new_user, png(300, 400)).json()
    client.post("/api/expenses", json={"merchant": "DMart", "amount": 10, "date": "2026-01-02",
                                       "category": "Groceries", "receipt_id": r3["receipt_id"]}, headers=new_user)
    assert client.delete(f"/api/receipts/{r3['receipt_id']}", headers=new_user).status_code == 409
    s = get_settings()
    files = pymongo.MongoClient(s.mongo_uri)[s.mongo_db]["receipts.files"]
    from bson import ObjectId
    old = datetime.now(timezone.utc) - timedelta(hours=s.orphan_receipt_hours + 1)
    files.update_many({"_id": {"$in": [ObjectId(r2["receipt_id"]), ObjectId(r3["receipt_id"])]}},
                      {"$set": {"metadata.uploaded_at": old}})
    from app.routers.receipts import cleanup_orphans
    removed = client.portal.call(cleanup_orphans)  # run on the app's event loop (Motor is loop-bound)
    assert removed >= 1
    assert client.get(f"/api/receipts/{r2['receipt_id']}/image", headers=new_user).status_code == 404
    assert client.get(f"/api/receipts/{r3['receipt_id']}/image", headers=new_user).status_code == 200


def test_missing_model_file_degrades(tmp_path):
    from app.services.classifier import CategoryModel
    m = CategoryModel(str(tmp_path / "nope.joblib"), auto_rebuild=False)
    assert m.status == "unavailable" and "not found" in m.error
    assert m.predict("DMart") is None


def test_corrupt_model_file_degrades(tmp_path):
    from app.services.classifier import CategoryModel
    bad = tmp_path / "bad.joblib"
    bad.write_bytes(b"this is not a pickle")
    m = CategoryModel(str(bad), auto_rebuild=False)
    assert m.status == "unavailable" and m.error


def test_api_reports_unavailable_model(client, new_user, monkeypatch, tmp_path):
    from app.services import classifier
    broken = classifier.CategoryModel(str(tmp_path / "missing.joblib"), auto_rebuild=False)
    monkeypatch.setattr(classifier, "_model", broken)
    h = client.get("/api/health").json()
    assert h["status"] == "degraded" and "category_model" in h["degraded"] and h["classifier"] is False
    s = client.post("/api/categories/suggest", json={"merchant": "DMart"}, headers=new_user).json()
    assert s["status"] == "unavailable" and s["category"] == "Uncategorised" and s["abstained"]
    e = client.post("/api/expenses", json={"merchant": "DMart", "amount": 50, "date": "2026-01-03"},
                    headers=new_user)
    assert e.status_code == 201 and e.json()["category"] == "Uncategorised"


def test_low_confidence_path_abstains(client, new_user, monkeypatch):
    from app.services import classifier
    model = classifier.get_model()
    monkeypatch.setitem(model.bundle, "abstain_threshold", 0.999)
    s = client.post("/api/categories/suggest", json={"merchant": "Some Shop"}, headers=new_user).json()
    assert s["status"] == "low_confidence" and s["abstained"] is True
    assert s["category"] in [a["category"] for a in s["alternatives"]]  # best guess is still reported
    e = client.post("/api/expenses", json={"merchant": "Some Shop", "amount": 50, "date": "2026-01-03"},
                    headers=new_user).json()
    assert e["category"] == "Uncategorised"
    # the user can file it later; Uncategorised is a valid filter but not a budget category
    assert client.get("/api/expenses?category=Uncategorised", headers=new_user).json()["total"] >= 1
    assert client.put("/api/budgets", json={"category": "Uncategorised", "amount": 10}, headers=new_user).status_code == 422


def test_confident_suggestion_has_explanation(client, new_user):
    s = client.post("/api/categories/suggest", json={"merchant": "HP Petrol Pump", "items": ["speed petrol"]},
                    headers=new_user).json()
    assert s["status"] == "confident" and s["category"] == "Transport & Fuel"
    tokens = [t["token"] for t in s["explanation"]]
    assert any("petrol" in t for t in tokens), tokens
    assert 0 < s["threshold"] < 1 and s["model_version"]


def test_model_endpoint(client):
    m = client.get("/api/model").json()
    assert m["category_model"]["status"] == "ready"
    assert "SYNTHETIC" in m["notes"][0]
    assert m["receipt_pipeline"]["review_threshold"] == 0.6
    assert m["anomaly_rule"]["z_threshold"] == 3.5


def test_login_rate_limit(client):
    body = {"name": "RL", "email": "ratelimit@example.com", "password": "secret123"}
    client.post("/api/auth/register", json=body)
    from app.config import get_settings
    for _ in range(get_settings().login_max_attempts):
        assert client.post("/api/auth/login", json={"email": body["email"], "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": body["email"], "password": "nope"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    # even the right password is refused while locked out
    assert client.post("/api/auth/login", json={"email": body["email"], "password": "secret123"}).status_code == 429


@pytest.mark.parametrize("secret", ["change-me-in-production", "short", ""])
def test_placeholder_jwt_secret_refused_in_production(secret):
    with pytest.raises(InsecureSecretError):
        check_jwt_secret(Settings(jwt_secret=secret, env="production"))


def test_placeholder_jwt_secret_replaced_in_development():
    s = check_jwt_secret(Settings(jwt_secret="change-me-in-production", env="development"))
    assert s.jwt_ephemeral and len(s.jwt_secret) >= 32 and s.jwt_secret != "change-me-in-production"
    real = "x" * 40
    assert check_jwt_secret(Settings(jwt_secret=real, env="production")).jwt_secret == real
