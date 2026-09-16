import os
import shutil
import tempfile
import uuid
from pathlib import Path

os.environ["JWT_SECRET"] = "test-secret-" + "x" * 32
os.environ["MONGO_DB"] = f"test_{uuid.uuid4().hex[:8]}"
# retrain writes the model file; point the app at a throwaway copy so tests never touch the real one
_tmp = Path(tempfile.mkdtemp())
_src = Path(__file__).resolve().parent.parent / "ml" / "artifacts" / "category_model.joblib"
shutil.copy(_src, _tmp / "model.joblib")
os.environ["MODEL_PATH"] = str(_tmp / "model.joblib")

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    import pymongo
    pymongo.MongoClient(get_settings().mongo_uri).drop_database(os.environ["MONGO_DB"])
    shutil.rmtree(_tmp, ignore_errors=True)


def _register(client):
    r = client.post("/api/auth/register", json={"name": "Test", "email": f"t{uuid.uuid4().hex[:6]}@example.com",
                                                "password": "secret123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def auth_headers(client):
    return _register(client)


@pytest.fixture
def new_user(client):
    """A fresh user per test, for tests that need an empty ledger."""
    return _register(client)
