"""Cas nominaux et limites de la creation de pack (F17)."""

from tests.support import login_header

_BODY = {"name": "Mini", "ram": 1, "cpu": 1, "vram": 1, "ssd": 1}


async def test_admin_creates_pack(client, iam):
    """Un administrateur cree un pack."""
    headers = await login_header(iam, "root@x.cm")
    response = client.post("/api/v1/admin/packs", headers=headers, json=_BODY)
    assert response.status_code == 201
    assert response.json()["name"] == "Mini"


async def test_user_cannot_create_pack(client, iam):
    """Un utilisateur simple recoit 403."""
    headers = await login_header(iam)
    response = client.post("/api/v1/admin/packs", headers=headers, json=_BODY)
    assert response.status_code == 403


def test_create_pack_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/admin/packs", json=_BODY).status_code == 401
