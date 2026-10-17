"""Cas nominaux et limites de la liste des reseaux (F7)."""

from tests.support import login_header


async def test_list_networks(client, iam):
    """Le projet liste ses reseaux."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    )
    response = client.get(f"/api/v1/projects/{project['id']}/networks", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_list_networks_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/networks").status_code == 401
