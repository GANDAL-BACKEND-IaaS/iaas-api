"""Cas nominaux et limites de la suppression de stockage (F11)."""

from app.shared.models.storages import Storage
from tests.support import add_storage, login_header


def _confirm(client, path, headers):
    preview = client.post(path, headers=headers, json={})
    assert preview.status_code == 200, preview.text
    return client.post(
        path, headers=headers, json={"confirmation_text": preview.json()["confirmation_text"]}
    )


async def test_delete_storage(client, db, iam):
    """La suppression retire le stockage meme s'il contient des donnees."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_storage(db, project["id"], "st-1")
    response = _confirm(
        client, f"/api/v1/projects/{project['id']}/storages/st-1/deletion", headers
    )
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert db.get(Storage, "st-1") is None


async def test_delete_storage_when_port_down(client, db, iam, storage_port):
    """Un stockage indisponible laisse la ressource en base."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_storage(db, project["id"], "st-1")
    preview = client.post(
        f"/api/v1/projects/{project['id']}/storages/st-1/deletion",
        headers=headers,
        json={},
    ).json()
    storage_port.available = False
    response = client.post(
        f"/api/v1/projects/{project['id']}/storages/st-1/deletion",
        headers=headers,
        json={"confirmation_text": preview["confirmation_text"]},
    )
    assert response.status_code == 503
    assert db.get(Storage, "st-1") is not None


def test_delete_storage_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/storages/st-1/deletion", json={})
    assert response.status_code == 401
