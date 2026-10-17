"""Cas nominaux et limites du rattachement d'une VM (F7, R21)."""

from tests.support import add_vm, login_header


async def test_attach_visible_vm(client, db, iam):
    """Une VM du projet rejoint le reseau."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_vm(db, project["id"], "vm-1")
    network = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}/vms",
        headers=headers,
        json={"vm_id": "vm-1"},
    )
    assert response.status_code == 200
    assert response.json()["vm_ids"] == ["vm-1"]


async def test_attach_unknown_vm(client, iam):
    """Une VM absente est introuvable."""
    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    network = client.post(
        f"/api/v1/projects/{project['id']}/networks", headers=headers, json={"name": "lan"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/networks/{network['id']}/vms",
        headers=headers,
        json={"vm_id": "missing"},
    )
    assert response.status_code == 404


def test_attach_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/networks/n1/vms", json={"vm_id": "vm-1"})
    assert response.status_code == 401
