"""Cas nominaux et limites de la consultation d'un stockage (F10)."""

from tests.support import add_storage, login_header


async def test_get_storage(client, db, iam):
    """Le proprietaire consulte un stockage de son projet."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_storage(db, project["id"], "st-1")
    response = client.get(f"/api/v1/projects/{project['id']}/storages/st-1", headers=headers)
    assert response.status_code == 200
    assert response.json()["size_gb"] == 100


async def test_get_storage_unknown(client, iam):
    """Un stockage absent est introuvable."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.get(f"/api/v1/projects/{project['id']}/storages/missing", headers=headers)
    assert response.status_code == 404


def test_get_storage_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/storages/st-1").status_code == 401
