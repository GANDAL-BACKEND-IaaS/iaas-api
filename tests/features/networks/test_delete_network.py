"""Cas nominaux et limites de la suppression de reseau (F7)."""

from app.shared.models.networks import Network
from tests.support import login_header


async def test_delete_network(client, db, iam):
    """Supprimer un reseau le retire du projet."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    network = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    ).json()
    response = client.delete(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}", headers=headers
    )
    assert response.status_code == 204
    assert db.get(Network, network["id"]) is None


def test_delete_network_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.delete("/api/v1/projects/p1/networks/n1").status_code == 401
