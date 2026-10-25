"""Cas nominaux et limites de la demande de modification de stockage (F9)."""

from tests.support import add_storage, login_header


async def test_request_update_storage_is_pending(client, db, iam):
    """La modification depose une demande sur la taille."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_storage(db, project["id"], "st-1")
    response = client.post(
        f"/api/v1/projects/{project['id']}/storages/st-1/update-requests",
        headers=headers,
        json={"size_gb": 20},
    )
    assert response.status_code == 202
    assert response.json()["kind"] == "storage_update"
    assert response.json()["payload"]["size_gb"] == 20


def test_request_update_storage_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post(
        "/api/v1/projects/p1/storages/st-1/update-requests", json={"size_gb": 20}
    )
    assert response.status_code == 401
