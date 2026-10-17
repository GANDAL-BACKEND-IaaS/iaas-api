"""Cas nominaux et limites du partage de stockage (F14)."""

from tests.support import add_storage, login_header


async def test_share_storage(client, db, iam):
    """Le partage depuis le projet d'origine devient actif."""
    headers = await login_header(iam)
    origin = client.post("/api/v1/projects", headers=headers, json={"name": "A"}).json()
    dest = client.post("/api/v1/projects", headers=headers, json={"name": "B"}).json()
    add_storage(db, origin["id"], "st-1")
    response = client.post(
        f"/api/v1/projects/{origin['id']}/storages/st-1/shares",
        headers=headers,
        json={"dest_project_id": dest["id"]},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "active"


def test_share_storage_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post(
        "/api/v1/projects/p1/storages/st-1/shares", json={"dest_project_id": "p2"}
    )
    assert response.status_code == 401
