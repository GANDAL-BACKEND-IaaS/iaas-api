"""Contrat d'erreur : enveloppe unique, y compris pour les erreurs de routage."""


def _headers(client, email="u@x.cm", password="pw"):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_unknown_route_uses_the_error_envelope(client):
    """Un 404 de routage ne doit pas renvoyer {"detail": ...}."""
    response = client.get("/api/v1/inconnu")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]
    assert "details" in body["error"]
    assert "detail" not in body


def test_wrong_method_uses_the_error_envelope(client):
    """Un 405 de routage passe aussi par l'enveloppe."""
    response = client.put("/api/v1/auth/login")
    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "details" in body["error"]


def test_missing_token_uses_the_error_envelope(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_validation_error_exposes_normalised_details(client):
    response = client.post("/api/v1/auth/login", json={"email": "x"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert isinstance(error["details"], list)
    assert any(item["field"] == "password" for item in error["details"])


def test_pagination_filter_rejects_zero_with_details(client):
    headers = _headers(client)
    response = client.get("/api/v1/packs?page=0", headers=headers)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any(item["field"] == "page" for item in error["details"])
