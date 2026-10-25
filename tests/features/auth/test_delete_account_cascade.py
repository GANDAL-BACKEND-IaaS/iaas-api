"""Suppression de compte : cascade des projets et nettoyage des contributions."""

from app.features.shares.service import create_share
from app.shared.enums import RequestKind, ResourceType
from app.shared.models.identities import UserRef
from app.shared.models.networks import Network
from app.shared.models.projects import Invitation, Membership, Project
from app.shared.models.requests import ResourceRequest
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm
from tests.support import add_project, add_storage, add_vm, own_project


def _login(client, email="u@x.cm", password="pw"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _headers(client, email="u@x.cm", password="pw"):
    response = _login(client, email, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_delete_owner_account_cascades_projects(client, db, iam):
    """Les projets dont l'utilisateur est proprietaire et leurs ressources disparaissent."""
    uid = await own_project(db, iam, "p1")
    add_vm(db, "p1", "vm-1")
    add_storage(db, "p1", "st-1")
    db.add(Network(id="net-1", project_id="p1", name="lan"))
    db.commit()
    headers = _headers(client)
    assert db.get(UserRef, uid) is not None

    response = client.delete("/api/v1/auth/me", headers=headers)
    assert response.status_code == 204
    assert db.get(Project, "p1") is None
    assert db.get(Vm, "vm-1") is None
    assert db.get(Storage, "st-1") is None
    assert db.get(Network, "net-1") is None
    assert db.get(UserRef, uid) is None
    assert _login(client).status_code == 401


async def test_delete_guest_account_cleans_memberships_and_contributions(client, db, iam):
    """Les projets d'autrui restent, mais appartenances et contributions sont nettoyees."""
    owner = await own_project(db, iam, "p1")
    await iam.create_project(owner, "p2")
    add_project(db, owner, "p2")
    add_vm(db, "p1", "vm-1")
    guest = iam.add_user("guest@x.cm", "pw")
    bob = iam.add_user("bob@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p1", ["vm.share"])
    await iam.invite_user(guest.user_id, "p2", ["vm.view"])
    db.add(
        Membership(
            project_id="p1",
            user_id=guest.user_id,
            role="guest",
            additional_rights=["vm.share"],
        )
    )
    db.add(
        Membership(
            project_id="p2",
            user_id=guest.user_id,
            role="guest",
            additional_rights=["vm.view"],
        )
    )
    share = await create_share(
        db,
        iam,
        user_id=guest.user_id,
        project_id="p1",
        resource_type=ResourceType.VM,
        resource_id="vm-1",
        dest_project_id="p2",
    )
    request = ResourceRequest(
        project_id="p2",
        author_id=guest.user_id,
        kind=RequestKind.VM_CREATE.value,
        status="pending",
        payload={"name": "web"},
    )
    invitation = Invitation(
        project_id="p2",
        inviter_id=guest.user_id,
        invitee_id=bob.user_id,
        status="sent",
    )
    received = Invitation(
        project_id="p2",
        inviter_id=owner,
        invitee_id=guest.user_id,
        status="sent",
    )
    db.add(request)
    db.add(invitation)
    db.add(received)
    db.commit()

    headers = _headers(client, "guest@x.cm")
    response = client.delete("/api/v1/auth/me", headers=headers)
    assert response.status_code == 204

    assert db.get(Project, "p1") is not None
    assert db.get(Project, "p2") is not None
    assert db.get(Vm, "vm-1") is not None
    assert db.query(Membership).filter_by(user_id=guest.user_id).count() == 0
    assert db.get(ResourceShare, share.id).status == "revoked"
    assert db.get(ResourceRequest, request.id).status == "cancelled"
    assert db.get(Invitation, invitation.id).status == "cancelled"
    assert db.get(Invitation, received.id).status == "cancelled"
    assert _login(client, "guest@x.cm").status_code == 401


async def test_delete_account_is_cancelled_when_infrastructure_fails(
    client, db, iam, hypervisor
):
    """Une panne externe annule la suppression et laisse le compte utilisable."""
    uid = await own_project(db, iam, "p1")
    add_vm(db, "p1", "vm-1")
    headers = _headers(client)
    hypervisor.available = False

    response = client.delete("/api/v1/auth/me", headers=headers)
    assert response.status_code == 503
    assert db.get(Project, "p1") is not None
    assert db.get(Vm, "vm-1") is not None
    assert db.get(UserRef, uid) is not None
    assert _login(client).status_code == 200
