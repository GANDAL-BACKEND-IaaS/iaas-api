from app.shared.models.identities import AdminRef, UserRef


def _login(client, email="u@x.cm", password="pw"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _headers(client, email="u@x.cm", password="pw"):
    return {"Authorization": f"Bearer {_login(client, email, password).json()['access_token']}"}


def test_login_ok_creates_local_reference(client, db):
    r = _login(client)
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    user_id = client.get("/api/v1/auth/me", headers=_headers(client)).json()["user_id"]
    assert db.get(UserRef, user_id) is not None

    _login(client)  # idempotent
    _login(client, "root@x.cm")
    admin_id = client.get("/api/v1/auth/me", headers=_headers(client, "root@x.cm")).json()["user_id"]
    assert db.get(AdminRef, admin_id) is not None and db.get(UserRef, admin_id) is None


def test_login_wrong_credentials(client):
    assert _login(client, password="nope").status_code == 401
    assert _login(client, email="inconnu@x.cm").status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    body = client.get("/api/v1/auth/me", headers=_headers(client)).json()
    assert body["email"] == "u@x.cm" and body["role"] == "user" and body["first_name"] == "Ulrich"


def test_update_returns_new_token(client):
    r = client.patch("/api/v1/auth/me", headers=_headers(client), json={"first_name": "Ulysse"})
    assert r.status_code == 200
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=new).json()
    assert me["first_name"] == "Ulysse" and me["last_name"] == "Kamga"


def test_update_email_conflict(client):
    r = client.patch("/api/v1/auth/me", headers=_headers(client), json={"email": "root@x.cm"})
    assert r.status_code == 409


def test_change_password(client):
    h = _headers(client)
    bad = client.post("/api/v1/auth/password", headers=h, json={"old_password": "x", "new_password": "secret1"})
    assert bad.status_code == 400
    ok = client.post("/api/v1/auth/password", headers=h, json={"old_password": "pw", "new_password": "secret1"})
    assert ok.status_code == 204
    assert _login(client, password="pw").status_code == 401
    assert _login(client, password="secret1").status_code == 200


def test_delete_account(client, db):
    h = _headers(client)
    user_id = client.get("/api/v1/auth/me", headers=h).json()["user_id"]
    assert client.delete("/api/v1/auth/me", headers=h).status_code == 204
    assert db.get(UserRef, user_id) is None
    assert _login(client).status_code == 401