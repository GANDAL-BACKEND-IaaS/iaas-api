"""Tests de la route POST /projects/{project_id}/networks (create_network)."""

from sqlalchemy import select

from app.shared.models.audit import AuditLog
from app.shared.models.networks import Network
from tests.support import login_header, own_project


async def test_create_network_requires_a_token(client):
    """Sans jeton, la route refuse avec 401 unauthorized."""
    response = client.request("POST", "/api/v1/projects/p1/networks", json={"name": "lan"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_create_network_by_owner_succeeds(client, db, iam):
    """Le proprietaire cree un reseau directement (F7, 201)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    response = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-prod"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "lan-prod"
    assert body["project_id"] == "p1"
    assert body["vm_ids"] == []
    assert "id" in body
    assert "created_at" in body

    # Verifie la persistence en base
    net = db.get(Network, body["id"])
    assert net is not None
    assert net.name == "lan-prod"

    # Verifie l'audit
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == "network.created", AuditLog.entity_id == body["id"])
    ).first()
    assert audit is not None
    assert audit.entity_type == "network"
    assert audit.data["name"] == "lan-prod"


async def test_create_network_by_guest_with_vm_network_right(client, db, iam):
    """Un invite disposant du droit vm.network peut creer un reseau."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    iam.add_user("guest@x.cm", "pw", "Guest", "User")
    uid = await iam.login("guest@x.cm", "pw")
    guest_identity = await iam.validate_token(uid.access_token)
    await iam.invite_user(guest_identity.user_id, "p1", ["vm.network", "vm.view"])

    headers = await login_header(iam, "guest@x.cm")
    response = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-guest"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "lan-guest"


async def test_create_network_by_guest_without_right_fails(client, db, iam):
    """Un invite sans le droit vm.network est refuse avec 403 forbidden."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    iam.add_user("guest2@x.cm", "pw", "Guest", "Two")
    uid = await iam.login("guest2@x.cm", "pw")
    guest_identity = await iam.validate_token(uid.access_token)
    await iam.invite_user(guest_identity.user_id, "p1", ["vm.view"])

    headers = await login_header(iam, "guest2@x.cm")
    response = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-fail"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_create_network_by_non_member_fails(client, db, iam):
    """Un utilisateur non membre du projet est refuse avec 403."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    iam.add_user("outsider@x.cm", "pw", "Out", "Sider")

    headers = await login_header(iam, "outsider@x.cm")
    response = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-out"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_create_network_in_nonexistent_project_fails(client, db, iam):
    """Projet inconnu -> 404 not_found."""
    headers = await login_header(iam, "u@x.cm")
    response = client.request(
        "POST", "/api/v1/projects/nonexistent/networks", headers=headers, json={"name": "lan"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_network_duplicate_slug_conflict(client, db, iam):
    """Deux reseaux avec un slug equivalent provoquent un conflit 409."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    r1 = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "Lan Web"})
    assert r1.status_code == 201

    r2 = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-web"})
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "conflict"


async def test_create_network_when_upstream_unavailable(client, db, iam, fake_network):
    """Si le groupe Reseau est en panne : 503 upstream_unavailable et aucun etat n'est ecrit."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    fake_network.available = False
    response = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-down"}
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "upstream_unavailable"

    # Verifie qu'aucune ligne n'a ete inseree
    networks = db.scalars(select(Network).where(Network.name == "lan-down")).all()
    assert len(networks) == 0
