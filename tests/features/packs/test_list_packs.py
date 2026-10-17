"""Cas nominaux et limites de la liste des packs (F17)."""

from app.shared.models.packs import Pack
from tests.support import login_header


async def test_list_packs_returns_catalog(client, db, iam):
    """Un utilisateur connecte lit le catalogue pagine."""
    db.add(Pack(name="Standard", ram=1, cpu=1, vram=1, ssd=1))
    db.commit()
    headers = await login_header(iam)
    response = client.get("/api/v1/packs", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Standard"


def test_list_packs_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/packs").status_code == 401
