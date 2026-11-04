"""Cas nominaux et limites de la creation de reseau (F7)."""

from tests.support import login_header


async def test_create_network(client, iam):
    """Un membre autorise cree un reseau dans son projet."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "lan"
    assert response.json()["vm_ids"] == []


async def test_create_network_when_port_down(client, iam, network):
    """Un reseau indisponible n'enregistre rien."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    network.available = False
    response = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    )
    assert response.status_code == 503


def test_create_network_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/projects/p1/networks", json={"name": "lan"}).status_code == 401
