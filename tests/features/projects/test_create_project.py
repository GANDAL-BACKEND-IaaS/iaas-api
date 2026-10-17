"""Cas nominaux et limites de la creation de projet (F12)."""

from tests.support import login_header


async def test_create_project_makes_caller_owner(client, iam):
    """L'appelant devient proprietaire du projet cree."""
    headers = await login_header(iam)
    response = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alpha"
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert body["owner_id"] == me["user_id"]


def test_create_project_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/projects", json={"name": "Alpha"}).status_code == 401
