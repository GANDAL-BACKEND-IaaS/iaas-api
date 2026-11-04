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


def test_register_creates_user_reference_and_returns_usable_token(client, db):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@x.cm",
            "password": "long-enough-password",
            "first_name": "New",
            "last_name": "User",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert set(payload) == {"access_token", "token_type", "expires_in"}
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    identity = client.get("/api/v1/auth/me", headers=headers)
    assert identity.status_code == 200 and identity.json()["role"] == "user"
    assert db.get(UserRef, identity.json()["user_id"]) is not None


def test_register_duplicate_email_returns_conflict(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": " U@X.CM ",
            "password": "long-enough-password",
            "first_name": "New",
            "last_name": "User",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_register_rejects_invalid_email_and_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid",
            "password": "short",
            "first_name": "New",
            "last_name": "User",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_admin_can_create_another_admin(client, iam, db):
    response = client.post(
        "/api/v1/admin/admins",
        headers=_headers(client, "root@x.cm"),
        json={
            "email": "new-admin@x.cm",
            "password": "long-enough-password",
            "first_name": "New",
            "last_name": "Admin",
        },
    )

    assert response.status_code == 201
    identity = response.json()
    assert identity["role"] == "admin"
    assert db.get(AdminRef, identity["user_id"]) is not None
    assert db.get(UserRef, identity["user_id"]) is None

    admin_headers = _headers(client, "new-admin@x.cm", "long-enough-password")
    assert client.post(
        "/api/v1/admin/profiles",
        headers=admin_headers,
        json={"name": "Nouveau profil", "rights": ["vm.view"]},
    ).status_code == 201


def test_only_admin_can_create_another_admin(client):
    body = {
        "email": "new-admin@x.cm",
        "password": "long-enough-password",
        "first_name": "New",
        "last_name": "Admin",
    }

    assert client.post("/api/v1/admin/admins", json=body).status_code == 401
    response = client.post(
        "/api/v1/admin/admins", headers=_headers(client), json=body
    )
    assert response.status_code == 403


def test_admin_can_list_all_users_with_pagination(client):
    response = client.get(
        "/api/v1/admin/users",
        headers=_headers(client, "root@x.cm"),
        params={"page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_items"] == 2
    assert payload["total_pages"] == 2
    assert payload["page"] == 1 and payload["page_size"] == 1
    assert len(payload["items"]) == 1
    assert set(payload["items"][0]) == {
        "user_id", "email", "first_name", "last_name", "role"
    }

    second_page = client.get(
        "/api/v1/admin/users",
        headers=_headers(client, "root@x.cm"),
        params={"page": 2, "page_size": 1},
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["role"] == "user"


def test_only_admin_can_list_users(client):
    assert client.get("/api/v1/admin/users").status_code == 401
    response = client.get("/api/v1/admin/users", headers=_headers(client))
    assert response.status_code == 403


def test_create_admin_duplicate_email_returns_conflict(client):
    response = client.post(
        "/api/v1/admin/admins",
        headers=_headers(client, "root@x.cm"),
        json={
            "email": "u@x.cm",
            "password": "long-enough-password",
            "first_name": "New",
            "last_name": "Admin",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


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