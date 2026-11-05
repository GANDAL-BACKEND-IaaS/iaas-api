"""Tests de la vue operationnelle admin d'un utilisateur."""

from app.application.ports.iam import IamError
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Invitation, Membership
from app.shared.models.requests import ResourceRequest
from app.shared.models.shares import ResourceShare
from tests.support import add_project, add_vm, login_header, own_project, user_id


async def test_admin_gets_user_overview_without_identity(client, db, iam):
    """Les ressources et relations sont regroupees sans dupliquer l'identite IAM."""
    target_id = await own_project(db, iam, "p1")
    await iam.create_project(target_id, "p2")
    add_project(db, target_id, "p2")
    add_vm(db, "p1", "vm-origin")
    add_vm(db, "p2", "vm-local")

    other_owner = iam.add_user("owner@x.cm", "pw")
    await iam.create_project(other_owner.user_id, "p3")
    add_project(db, other_owner.user_id, "p3")
    await iam.invite_user(target_id, "p3", ["vm.view"])
    db.add(
        Membership(
            project_id="p3",
            user_id=target_id,
            role="guest",
            additional_rights=["vm.view"],
        )
    )

    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-origin",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by=target_id,
            status="active",
        )
    )
    db.add(Network(id="net-p2", project_id="p2", name="private"))
    db.add(NetworkVm(network_id="net-p2", vm_id="vm-origin"))
    db.add_all(
        [
            Invitation(
                id="invite-sent",
                project_id="p1",
                inviter_id=target_id,
                invitee_id=other_owner.user_id,
                status="sent",
                additional_rights=[],
            ),
            Invitation(
                id="invite-received",
                project_id="p3",
                inviter_id=other_owner.user_id,
                invitee_id=target_id,
                status="accepted",
                additional_rights=["vm.view"],
            ),
            ResourceRequest(
                id="request-1",
                project_id="p1",
                author_id=target_id,
                kind="vm_create",
                status="pending",
                payload={"name": "new-vm"},
            ),
        ]
    )
    db.commit()

    response = client.get(
        f"/api/v1/admin/users/{target_id}/overview",
        headers=await login_header(iam, "root@x.cm"),
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "email" not in result and "first_name" not in result and "user_id" not in result
    projects = {project["id"]: project for project in result["projects"]}
    assert set(projects) == {"p1", "p2", "p3"}
    assert projects["p1"]["role"] == "owner"
    assert "vm.view" in projects["p1"]["rights"]
    assert projects["p3"]["role"] == "guest"
    assert projects["p3"]["rights"] == ["vm.view"]
    assert [vm["id"] for vm in projects["p1"]["vms"]] == ["vm-origin"]
    assert {vm["id"]: vm["shared"] for vm in projects["p2"]["vms"]} == {
        "vm-local": False,
        "vm-origin": True,
    }
    assert projects["p2"]["networks"][0]["vm_ids"] == ["vm-origin"]
    assert {invitation["id"] for invitation in result["invitations"]} == {
        "invite-sent",
        "invite-received",
    }
    assert [request["id"] for request in result["requests"]] == ["request-1"]
    assert [share["resource_id"] for share in result["shares"]] == ["vm-origin"]


async def test_overview_for_user_without_projects_returns_empty_collections(client, iam):
    """Un compte sans activite dispose de listes vides dans chaque rubrique."""
    response = client.get(
        f"/api/v1/admin/users/{(await user_id(iam, 'root@x.cm'))}/overview",
        headers=await login_header(iam, "root@x.cm"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "projects": [],
        "invitations": [],
        "requests": [],
        "shares": [],
    }


async def test_user_overview_requires_admin(client, iam):
    """Seul un administrateur peut consulter les donnees operationnelles."""
    target_id = await user_id(iam)

    assert client.get(f"/api/v1/admin/users/{target_id}/overview").status_code == 401
    response = client.get(
        f"/api/v1/admin/users/{target_id}/overview",
        headers=await login_header(iam),
    )
    assert response.status_code == 403


async def test_user_overview_returns_not_found_when_iam_has_no_account(client, iam):
    """Une reference locale sans compte IAM ne produit pas une fiche fictive."""
    target_id = await user_id(iam)
    await iam.delete_account(target_id)

    response = client.get(
        f"/api/v1/admin/users/{target_id}/overview",
        headers=await login_header(iam, "root@x.cm"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_user_overview_reports_iam_unavailable(client, iam, monkeypatch):
    """Une panne IAM est renvoyee comme indisponibilite amont explicite."""
    target_id = await user_id(iam)

    async def fail_get_user(_user_id):
        raise IamError("IAM unavailable")

    monkeypatch.setattr(iam, "get_user", fail_get_user)
    response = client.get(
        f"/api/v1/admin/users/{target_id}/overview",
        headers=await login_header(iam, "root@x.cm"),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"
