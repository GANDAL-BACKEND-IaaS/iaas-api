"""Tests de la route DELETE /projects/{project_id}/networks/{network_id}/vms/{vm_id} (detach_vm)."""

from sqlalchemy import select

from app.shared.models.audit import AuditLog
from app.shared.models.networks import NetworkVm
from tests.support import add_vm, login_header, own_project


async def test_detach_vm_from_network_requires_a_token(client):
    """Sans jeton -> 401 unauthorized."""
    response = client.request("DELETE", "/api/v1/projects/p1/networks/net-1/vms/vm-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_detach_vm_nominal(client, db, iam):
    """Retrait d'une VM du reseau (F7, 200)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-detach"})
    net_id = net_res.json()["id"]

    add_vm(db, project_id="p1", vm_id="vm-1")
    client.request("POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-1"})

    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}/vms/vm-1", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "vm-1" not in body["vm_ids"]

    # Verifie en base
    assert db.get(NetworkVm, (net_id, "vm-1")) is None

    # Verifie l'audit
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "network.vm_detached", AuditLog.entity_id == net_id)
    ).first()
    assert audit is not None
    assert audit.data["vm_id"] == "vm-1"


async def test_detach_vm_idempotence(client, db, iam):
    """Retirer une VM deja absente du reseau est idempotent (200)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-absent"})
    net_id = net_res.json()["id"]

    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}/vms/vm-never-in", headers=headers)
    assert response.status_code == 200


async def test_detach_vm_by_guest_without_right_fails(client, db, iam):
    """Un invite sans vm.network est refuse (403)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    owner_headers = await login_header(iam, "u@x.cm")
    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=owner_headers, json={"name": "lan-sec"})
    net_id = net_res.json()["id"]

    iam.add_user("viewer@x.cm", "pw", "View", "Er")
    uid = await iam.login("viewer@x.cm", "pw")
    viewer_identity = await iam.validate_token(uid.access_token)
    await iam.invite_user(viewer_identity.user_id, "p1", ["vm.view"])

    viewer_headers = await login_header(iam, "viewer@x.cm")
    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}/vms/vm-1", headers=viewer_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_detach_vm_when_upstream_unavailable(client, db, iam, fake_network):
    """Si le groupe Reseau est indisponible : 503 et le lien reste intact en base."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    net_res = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-fail-detach"})
    net_id = net_res.json()["id"]
    add_vm(db, project_id="p1", vm_id="vm-keep")

    client.request("POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-keep"})

    fake_network.available = False
    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}/vms/vm-keep", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"

    # Verifie que le lien est toujours en base
    assert db.get(NetworkVm, (net_id, "vm-keep")) is not None
