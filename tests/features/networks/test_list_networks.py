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
    assert response.json()["total_items"] == 1


async def test_list_networks_with_vm_view_only(client, iam):
    """vm.view suffit pour lire les reseaux."""
    owner = await login_header(iam)
    project = client.post("/api/v1/projects", headers=owner, json={"name": "Alpha"}).json()
    client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=owner, json={"name": "lan"}
    )
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, project["id"], ["vm.view"])
    headers = await login_header(iam, "guest@x.cm")
    response = client.get(f"/api/v1/projects/{project['id']}/networks", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_items"] == 1


async def test_list_networks_with_vm_network_only_is_forbidden(client, iam):
    """vm.network est un droit d'ecriture, pas de lecture."""
    owner = await login_header(iam)
    project = client.post("/api/v1/projects", headers=owner, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, project["id"], ["vm.network"])
    headers = await login_header(iam, "guest@x.cm")
    response = client.get(f"/api/v1/projects/{project['id']}/networks", headers=headers)
    assert response.status_code == 403


def test_list_networks_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/networks").status_code == 401
