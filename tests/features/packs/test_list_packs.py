"""Cas nominaux et limites de la liste des packs (F17)."""

from tests.support import add_pack, login_header


async def test_list_packs_returns_catalog(client, db, iam):
    """Un utilisateur connecte lit le catalogue pagine."""
    add_pack(db, "Standard", ram_gb=1, vcpu=1, vram_gb=1, ssd_gb=1)
    headers = await login_header(iam)
    response = client.get("/api/v1/packs", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_items"] == 1
    assert response.json()["items"][0]["name"] == "Standard"


def test_list_packs_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/packs").status_code == 401
