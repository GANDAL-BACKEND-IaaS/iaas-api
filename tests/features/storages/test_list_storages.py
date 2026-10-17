"""Cas nominaux et limites de la liste des stockages (F10)."""

from tests.support import add_storage, login_header


async def test_list_storages(client, db, iam):
    """Le proprietaire voit les stockages de son projet."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_storage(db, project["id"], "st-1")
    response = client.get(f"/api/v1/projects/{project['id']}/storages", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["shared"] is False


def test_list_storages_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/storages").status_code == 401
