"""Cas nominaux et limites de la suppression de projet (F12, R23)."""

from app.shared.models.projects import Project
from app.shared.models.vms import Vm
from tests.support import add_vm, login_header


async def test_owner_deletes_project_and_its_vm(client, db, iam):
    """La suppression retire le projet et ses VMs."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_vm(db, created["id"], "vm-1")
    response = client.post(
        f"/api/v1/projects/{created['id']}/deletion", headers=headers, json={"confirm": True}
    )
    assert response.status_code == 204
    assert db.get(Project, created["id"]) is None
    assert db.get(Vm, "vm-1") is None


async def test_guest_cannot_delete_project(client, iam):
    """Un invite ne supprime pas le projet."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, created["id"], ["vm.delete"])
    guest_headers = await login_header(iam, "guest@x.cm")
    response = client.post(
        f"/api/v1/projects/{created['id']}/deletion",
        headers=guest_headers,
        json={"confirm": True},
    )
    assert response.status_code == 403


def test_delete_project_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/deletion", json={"confirm": True})
    assert response.status_code == 401
