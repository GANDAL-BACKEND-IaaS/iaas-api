"""Cas nominaux et limites du retrait d'une VM d'un reseau (F7)."""

from tests.support import add_vm, login_header


async def test_detach_vm(client, db, iam):
    """Retirer une VM la sort du reseau."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_vm(db, project["id"], "vm-1")
    network = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}/vms",
        headers=headers,
        json={"vm_id": "vm-1"},
    )
    response = client.delete(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}/vms/vm-1",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["vm_ids"] == []


def test_detach_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.delete("/api/v1/projects/p1/networks/n1/vms/vm-1").status_code == 401
