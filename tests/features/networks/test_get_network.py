"""Lecture d'un reseau : `vm.view` est le droit de lecture (F7, A-01)."""

from tests.support import login_header


async def _project_with_network(client, iam):
    owner = await login_header(iam)
    project = client.post("/api/v1/projects", headers=owner, json={"name": "Alpha"}).json()
    network = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=owner, json={"name": "lan"}
    ).json()
    return owner, project, network


async def test_get_network_with_vm_view_only(client, iam):
    """Un membre avec vm.view lit le reseau."""
    _, project, network = await _project_with_network(client, iam)
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, project["id"], ["vm.view"])
    headers = await login_header(iam, "guest@x.cm")
    response = client.get(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "lan"


async def test_get_network_with_vm_network_only_is_forbidden(client, iam):
    """vm.network seul ne suffit pas pour lire un reseau."""
    _, project, network = await _project_with_network(client, iam)
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, project["id"], ["vm.network"])
    headers = await login_header(iam, "guest@x.cm")
    response = client.get(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}", headers=headers
    )
    assert response.status_code == 403
