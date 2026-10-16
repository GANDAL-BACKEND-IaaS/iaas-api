"""Tests de la route PATCH /projects/{project_id}/networks/{network_id} (update_network)."""

from sqlalchemy import select

from app.shared.models.audit import AuditLog
from tests.support import login_header, own_project


async def test_update_network_requires_a_token(client):
    """Sans jeton -> 401 unauthorized."""
    response = client.request("PATCH", "/api/v1/projects/p1/networks/net-1", json={"name": "new-name"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_update_network_by_owner_succeeds(client, db, iam):
    """Le proprietaire peut renommer un reseau."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-initial"}
    )
    net_id = create_res.json()["id"]

    response = client.request(
        "PATCH", f"/api/v1/projects/p1/networks/{net_id}", headers=headers, json={"name": "lan-renamed"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == net_id
    assert body["name"] == "lan-renamed"

    # Verifie l'audit
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "network.renamed", AuditLog.entity_id == net_id)
    ).first()
    assert audit is not None
    assert audit.data["old_name"] == "lan-initial"
    assert audit.data["new_name"] == "lan-renamed"


async def test_update_network_by_guest_with_vm_network(client, db, iam):
    """Un invite avec vm.network peut renommer le reseau."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    owner_headers = await login_header(iam, "u@x.cm")
    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=owner_headers, json={"name": "lan-alpha"}
    )
    net_id = create_res.json()["id"]

    iam.add_user("member@x.cm", "pw", "Mem", "Ber")
    uid = await iam.login("member@x.cm", "pw")
    member_identity = await iam.validate_token(uid.access_token)
    await iam.invite_user(member_identity.user_id, "p1", ["vm.network"])

    member_headers = await login_header(iam, "member@x.cm")
    response = client.request(
        "PATCH", f"/api/v1/projects/p1/networks/{net_id}", headers=member_headers, json={"name": "lan-beta"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "lan-beta"


async def test_update_network_by_guest_without_right_fails(client, db, iam):
    """Un invite sans vm.network est refuse avec 403."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    owner_headers = await login_header(iam, "u@x.cm")
    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=owner_headers, json={"name": "lan-gamma"}
    )
    net_id = create_res.json()["id"]

    iam.add_user("viewer@x.cm", "pw", "View", "Er")
    uid = await iam.login("viewer@x.cm", "pw")
    viewer_identity = await iam.validate_token(uid.access_token)
    await iam.invite_user(viewer_identity.user_id, "p1", ["vm.view"])

    viewer_headers = await login_header(iam, "viewer@x.cm")
    response = client.request(
        "PATCH", f"/api/v1/projects/p1/networks/{net_id}", headers=viewer_headers, json={"name": "lan-delta"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_update_network_conflict_slug(client, db, iam):
    """Renommer vers un slug deja existant renvoie 409 conflict."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-one"})
    r2 = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-two"})
    net_two_id = r2.json()["id"]

    # Tentative de renommer lan-two en lan-one
    response = client.request(
        "PATCH", f"/api/v1/projects/p1/networks/{net_two_id}", headers=headers, json={"name": "lan-one"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
