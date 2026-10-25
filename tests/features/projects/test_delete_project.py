"""Cas nominaux et limites de la suppression de projet (F12, R23)."""

from app.shared.models.projects import Project
from app.shared.models.vms import Vm
from tests.support import add_vm, login_header


def _confirm(client, path, headers):
    """Joue le protocole en deux temps et retourne la reponse finale."""
    preview = client.post(path, headers=headers, json={})
    assert preview.status_code == 200, preview.text
    text = preview.json()["confirmation_text"]
    return client.post(path, headers=headers, json={"confirmation_text": text})


async def test_owner_deletes_project_and_its_vm(client, db, iam):
    """La suppression retire le projet et ses VMs."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    add_vm(db, created["id"], "vm-1")
    response = _confirm(
        client, f"/api/v1/projects/{created['id']}/deletion", headers
    )
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert db.get(Project, created["id"]) is None
    assert db.get(Vm, "vm-1") is None


async def test_owner_deletes_project_cascade(client, db, iam):
    """La suppression du projet retire aussi ses VMs, stockages, reseaux et partages."""
    from app.shared.enums import ShareStatus
    from app.shared.models.networks import Network
    from app.shared.models.shares import ResourceShare
    from app.shared.models.storages import Storage
    from tests.support import add_project, add_storage, own_project

    uid = await own_project(db, iam, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p2")
    add_vm(db, "p1", "vm-1")
    add_storage(db, "p1", "st-1")
    db.add(Network(id="net-1", project_id="p1", name="lan"))
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by=uid,
            status=ShareStatus.ACTIVE.value,
        )
    )
    db.commit()
    headers = await login_header(iam)
    response = _confirm(client, "/api/v1/projects/p1/deletion", headers)
    assert response.status_code == 200
    assert db.get(Project, "p1") is None
    assert db.get(Vm, "vm-1") is None
    assert db.get(Storage, "st-1") is None
    assert db.get(Network, "net-1") is None
    assert db.query(ResourceShare).count() == 0


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
        json={},
    )
    assert response.status_code == 403


def test_delete_project_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/deletion", json={})
    assert response.status_code == 401
