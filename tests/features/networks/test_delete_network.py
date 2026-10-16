"""Tests de la route DELETE /projects/{project_id}/networks/{network_id} (delete_network)."""

from sqlalchemy import select

from app.shared.models.audit import AuditLog
from app.shared.models.networks import Network, NetworkVm
from tests.support import add_vm, login_header, own_project


async def test_delete_network_requires_a_token(client):
    """Sans jeton -> 401 unauthorized."""
    response = client.request("DELETE", "/api/v1/projects/p1/networks/net-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_delete_network_nominal(client, db, iam):
    """Suppression d'un reseau : 204 No Content et suppression en cascade des liens."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-del-ok"}
    )
    net_id = create_res.json()["id"]

    add_vm(db, project_id="p1", vm_id="vm-linked")
    client.request("POST", f"/api/v1/projects/p1/networks/{net_id}/vms", headers=headers, json={"vm_id": "vm-linked"})

    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}", headers=headers)
    assert response.status_code == 204

    # Verifie suppression en base
    assert db.get(Network, net_id) is None
    assert db.get(NetworkVm, (net_id, "vm-linked")) is None

    # Verifie audit
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "network.deleted", AuditLog.entity_id == net_id)
    ).first()
    assert audit is not None
    assert audit.data["name"] == "lan-del-ok"


async def test_delete_network_by_guest_without_right_fails(client, db, iam):
    """Invite sans vm.network -> 403 forbidden."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    owner_headers = await login_header(iam, "u@x.cm")
    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=owner_headers, json={"name": "lan-guard"}
    )
    net_id = create_res.json()["id"]

    iam.add_user("viewer@x.cm", "pw", "V", "E")
    uid = await iam.login("viewer@x.cm", "pw")
    viewer_id = (await iam.validate_token(uid.access_token)).user_id
    await iam.invite_user(viewer_id, "p1", ["vm.view"])

    viewer_headers = await login_header(iam, "viewer@x.cm")
    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}", headers=viewer_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_delete_network_nonexistent_fails(client, db, iam):
    """Reseau inexistant -> 404 not_found."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    response = client.request("DELETE", "/api/v1/projects/p1/networks/unknown-net", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_delete_network_from_another_project_fails(client, db, iam):
    """Suppression d'un reseau de p1 sous l'URL de p2 -> 404 (pas de fuite)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    await own_project(db, iam, project_id="p2", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-p1-del"}
    )
    net_id = create_res.json()["id"]

    response = client.request("DELETE", f"/api/v1/projects/p2/networks/{net_id}", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_delete_network_when_upstream_unavailable(client, db, iam, fake_network):
    """En cas de panne du service reseau : 503 et le reseau reste en base."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-fail-del"}
    )
    net_id = create_res.json()["id"]

    fake_network.available = False
    response = client.request("DELETE", f"/api/v1/projects/p1/networks/{net_id}", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"

    # Verifie qu'il est toujours en base
    assert db.get(Network, net_id) is not None
