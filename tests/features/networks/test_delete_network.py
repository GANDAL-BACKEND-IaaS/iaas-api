"""Cas nominaux et limites de la suppression de reseau (F7)."""

from app.shared.models.networks import Network
from tests.support import login_header


def _confirm(client, path, headers):
    preview = client.post(path, headers=headers, json={})
    assert preview.status_code == 200, preview.text
    return client.post(
        path, headers=headers, json={"confirmation_text": preview.json()["confirmation_text"]}
    )


async def test_delete_network(client, db, iam):
    """Supprimer un reseau le retire du projet."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    network = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    ).json()
    response = _confirm(
        client,
        f"/api/v1/projects/{project['id']}/networks/{network['id']}/deletion",
        headers,
    )
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert db.get(Network, network["id"]) is None


def test_delete_network_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/networks/n1/deletion", json={})
    assert response.status_code == 401
