"""Retrait d'un membre : contributions invalidees et partages conditionnels."""

from app.features.shares.service import create_share
from app.shared.enums import RequestKind, ResourceType
from app.shared.models.projects import Invitation, Membership
from app.shared.models.requests import ResourceRequest
from app.shared.models.shares import ResourceShare
from tests.support import add_project, add_vm, login_header, user_id


async def _owner_and_guest(db, iam):
    owner = await user_id(iam)
    await iam.create_project(owner, "p1")
    await iam.create_project(owner, "p2")
    add_project(db, owner, "p1")
    add_project(db, owner, "p2")
    guest = iam.add_user("guest@x.cm", "pw")
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
    db.commit()
    return owner, guest


async def test_removal_cancels_pending_requests_and_invitations(client, db, iam):
    """Les demandes et invitations en attente du membre sortant sont annulees."""
    _, guest = await _owner_and_guest(db, iam)
    invitee = iam.add_user("bob@x.cm", "pw")
    invitation = Invitation(
        project_id="p1",
        inviter_id=guest.user_id,
        invitee_id=invitee.user_id,
        status="sent",
    )
    request = ResourceRequest(
        project_id="p1",
        author_id=guest.user_id,
        kind=RequestKind.VM_CREATE.value,
        status="pending",
        payload={"name": "web"},
    )
    db.add(invitation)
    db.add(request)
    db.commit()

    response = client.delete(
        f"/api/v1/projects/p1/members/{guest.user_id}",
        headers=await login_header(iam),
    )
    assert response.status_code == 204
    assert db.get(Invitation, invitation.id).status == "cancelled"
    assert db.get(ResourceRequest, request.id).status == "cancelled"


async def test_share_is_kept_while_creator_belongs_to_the_other_project(client, db, iam):
    """Le partage reste tant que le createur est membre de l'autre projet."""
    _, guest = await _owner_and_guest(db, iam)
    add_vm(db, "p1")
    share = await create_share(
        db,
        iam,
        user_id=guest.user_id,
        project_id="p1",
        resource_type=ResourceType.VM,
        resource_id="vm-1",
        dest_project_id="p2",
    )
    headers = await login_header(iam)

    first = client.delete(f"/api/v1/projects/p1/members/{guest.user_id}", headers=headers)
    assert first.status_code == 204
    assert db.get(ResourceShare, share.id).status == "active"

    second = client.delete(f"/api/v1/projects/p2/members/{guest.user_id}", headers=headers)
    assert second.status_code == 204
    assert db.get(ResourceShare, share.id).status == "revoked"


async def test_removal_does_not_touch_shares_created_by_others(client, db, iam):
    """Seuls les partages crees par le membre sortant sont examines."""
    owner, guest = await _owner_and_guest(db, iam)
    add_vm(db, "p1")
    share = await create_share(
        db,
        iam,
        user_id=owner,
        project_id="p1",
        resource_type=ResourceType.VM,
        resource_id="vm-1",
        dest_project_id="p2",
    )
    response = client.delete(
        f"/api/v1/projects/p1/members/{guest.user_id}",
        headers=await login_header(iam),
    )
    assert response.status_code == 204
    assert db.get(ResourceShare, share.id).status == "active"


async def test_network_outage_keeps_member_and_share(client, db, iam, network):
    """Si le detachement reseau echoue, le retrait est annule."""
    _, guest = await _owner_and_guest(db, iam)
    add_vm(db, "p1")
    share = await create_share(
        db,
        iam,
        user_id=guest.user_id,
        project_id="p1",
        resource_type=ResourceType.VM,
        resource_id="vm-1",
        dest_project_id="p2",
    )
    headers = await login_header(iam)
    assert client.delete(
        f"/api/v1/projects/p1/members/{guest.user_id}", headers=headers
    ).status_code == 204

    network.available = False
    response = client.delete(
        f"/api/v1/projects/p2/members/{guest.user_id}", headers=headers
    )
    assert response.status_code == 503
    assert db.get(ResourceShare, share.id).status == "active"
    assert db.query(Membership).filter_by(project_id="p2", user_id=guest.user_id).one()
