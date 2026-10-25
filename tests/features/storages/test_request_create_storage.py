"""Cas nominaux et limites de la demande de creation de stockage (F8)."""

from tests.support import login_header


async def test_request_create_storage_is_pending(client, iam):
    """La creation depose une demande, sans creer le stockage."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/storages",
        headers=headers,
        json={"name": "docs", "size_gb": 10},
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "storage_create"
    assert response.json()["status"] == "pending"


def test_request_create_storage_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/storages", json={"name": "docs", "size_gb": 10})
    assert response.status_code == 401
