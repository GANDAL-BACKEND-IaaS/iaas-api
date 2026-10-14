"""Cas nominaux et limites de list_shares."""

from app.application.ports.iam import GlobalRole
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
        db, iam, user_id=uid, resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    rows, total = await list_shares(
        db, iam, actor_id=uid, actor_role=GlobalRole.USER, params=PageParams(),
    )
    assert total == 1
    assert rows[0].resource_id == "vm-1"
    stranger = iam.add_user("stranger@x.cm", "pw")
    empty, empty_total = await list_shares(
        db, iam, actor_id=stranger.user_id, actor_role=GlobalRole.USER, params=PageParams(page=1, page_size=5),
    )
    assert empty == []
    assert empty_total == 0


async def test_admin_sees_every_share(db, iam):
    """L'administrateur liste tous les partages."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    await create_share(
        db, iam, user_id=uid, resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    admin = await user_id(iam, "root@x.cm")
    _, total = await list_shares(
        db, iam, actor_id=admin, actor_role=GlobalRole.ADMIN, params=PageParams(),
    )
    assert total == 1
