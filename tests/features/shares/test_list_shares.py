"""Cas nominaux et limites de list_shares (extension, sans bypass admin)."""

from app.core.pagination import PageParams
from app.features.shares.service import create_share, list_shares
from app.shared.enums import ResourceType
from tests.support import add_project, add_vm, user_id


async def test_member_lists_share_and_stranger_sees_none(db, iam):
    """Le membre voit le partage. Un utilisateur sans projet n'en voit aucun."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    await create_share(
        db, iam, user_id=uid, project_id="p1", resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    rows, total = await list_shares(
        db, iam, user_id=uid, params=PageParams(),
    )
    assert total == 1
    assert rows[0].resource_id == "vm-1"
    stranger = iam.add_user("stranger@x.cm", "pw")
    empty, empty_total = await list_shares(
        db, iam, user_id=stranger.user_id, params=PageParams(page=1, page_size=5),
    )
    assert empty == []
    assert empty_total == 0


async def test_admin_without_membership_sees_no_share(db, iam):
    """Un administrateur ne voit pas les partages des utilisateurs."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    await create_share(
        db, iam, user_id=uid, project_id="p1", resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    admin = await user_id(iam, "root@x.cm")
    rows, total = await list_shares(db, iam, user_id=admin, params=PageParams())
    assert rows == []
    assert total == 0


async def test_guest_without_view_right_sees_no_share(db, iam):
    """Un membre sans vm.view ne voit pas le partage dans la liste globale."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    await create_share(
        db, iam, user_id=uid, project_id="p1", resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p2", ["vm.network"])
    rows, total = await list_shares(db, iam, user_id=guest.user_id, params=PageParams())
    assert rows == []
    assert total == 0
    await iam.update_rights(guest.user_id, "p2", ["vm.view"])
    rows, total = await list_shares(db, iam, user_id=guest.user_id, params=PageParams())
    assert total == 1
    assert rows[0].resource_id == "vm-1"
