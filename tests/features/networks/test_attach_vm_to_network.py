"""Tests de la route POST /projects/{project_id}/networks/{network_id}/vms (attach_vm)."""

from sqlalchemy import select

from app.shared.enums import ShareStatus, VmState
from app.shared.models.audit import AuditLog
from app.shared.models.networks import NetworkVm
from app.shared.models.shares import ResourceShare
from tests.support import add_storage, add_vm, login_header, own_project


async def test_attach_vm_to_network_requires_a_token(client):
    """Sans jeton -> 401 unauthorized."""
    response = client.request("POST", "/api/v1/projects/p1/networks/net-1/vms", json={"vm_id": "vm-1"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_attach_origin_vm_succeeds(client, db, iam):
    """Rattache une VM d'origine du projet (F7, 200)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-1"})
    net_id = net_res.json()["id"]

    add_vm(db, project_id="p1", vm_id="vm-1")

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-1"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == net_id
    assert "vm-1" in body["vm_ids"]

    # Verifie la liaison en base
    link = db.get(NetworkVm, (net_id, "vm-1"))
    assert link is not None

    # Verifie l'audit
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "network.vm_attached", AuditLog.entity_id == net_id)
    ).first()
    assert audit is not None
    assert audit.data["vm_id"] == "vm-1"


async def test_attach_shared_vm_with_active_share_succeeds(client, db, iam):
    """Rattache une VM issue d'un autre projet mais partagee activement (R21)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    await own_project(db, iam, project_id="p2", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-p1"})
    net_id = net_res.json()["id"]

    # VM creee dans p2
    add_vm(db, project_id="p2", vm_id="vm-p2")

    # Partage actif vers p1
    share = ResourceShare(
        resource_type="vm",
        resource_id="vm-p2",
        origin_project_id="p2",
        dest_project_id="p1",
        created_by="u1",
        status=ShareStatus.ACTIVE.value,
    )
    db.add(share)
    db.commit()

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-p2"}
    )
    assert response.status_code == 200
    assert "vm-p2" in response.json()["vm_ids"]


async def test_attach_unshared_vm_fails(client, db, iam):
    """Une VM d'un autre projet sans partage actif est refusee (403 forbidden)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    await own_project(db, iam, project_id="p2", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-iso"})
    net_id = net_res.json()["id"]

    add_vm(db, project_id="p2", vm_id="vm-secret")

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-secret"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_attach_revoked_share_vm_fails(client, db, iam):
    """Une VM avec un partage revoque n'est plus visible et est refusee (403)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    await own_project(db, iam, project_id="p2", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-rev"})
    net_id = net_res.json()["id"]

    add_vm(db, project_id="p2", vm_id="vm-revoked")
    share = ResourceShare(
        resource_type="vm",
        resource_id="vm-revoked",
        origin_project_id="p2",
        dest_project_id="p1",
        created_by="u1",
        status=ShareStatus.REVOKED.value,
    )
    db.add(share)
    db.commit()

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-revoked"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_attach_storage_is_rejected(client, db, iam):
    """R22 : un espace de stockage ne peut jamais etre mis en reseau."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-storage"})
    net_id = net_res.json()["id"]

    add_storage(db, project_id="p1", storage_id="st-1")

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "st-1"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


async def test_attach_nonexistent_vm_fails(client, db, iam):
    """VM inexistante -> 404 not_found."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-ghost"})
    net_id = net_res.json()["id"]

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-unknown"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_attach_deleting_vm_fails(client, db, iam):
    """VM en cours de suppression -> 409 invalid_state."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-del"})
    net_id = net_res.json()["id"]

    add_vm(db, project_id="p1", vm_id="vm-del", state=VmState.DELETING.value)

    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-del"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


async def test_attach_vm_idempotence(client, db, iam):
    """Rattacher une VM deja presente ne leve pas d'erreur (idempotent, 200)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-idem"})
    net_id = net_res.json()["id"]
    add_vm(db, project_id="p1", vm_id="vm-1")

    r1 = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-1"}
    )
    assert r1.status_code == 200

    r2 = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-1"}
    )
    assert r2.status_code == 200
    assert r2.json()["vm_ids"] == ["vm-1"]


async def test_attach_vm_when_upstream_unavailable(client, db, iam, fake_network):
    """En cas de panne du service reseau : 503 et aucun lien en base."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-err"})
    net_id = net_res.json()["id"]
    add_vm(db, project_id="p1", vm_id="vm-err")

    fake_network.available = False
    response = client.request(
        "POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-err"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"

    # Verifie qu'aucun lien n'a ete cree
    link = db.get(NetworkVm, (net_id, "vm-err"))
    assert link is None
