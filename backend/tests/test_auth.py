def test_health(client):
    assert client.get("/api/health").json()["db"] == "connected"


def test_register_login_me(client):
    body = {"name": "Asha", "email": "asha@example.com", "password": "secret123"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    assert client.post("/api/auth/register", json=body).status_code == 409
    assert client.post("/api/auth/login", json={"email": body["email"], "password": "wrong"}).status_code == 401
    tok = client.post("/api/auth/login", json={"email": body["email"], "password": "secret123"}).json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["email"] == "asha@example.com"
    assert client.get("/api/auth/me").status_code == 401
