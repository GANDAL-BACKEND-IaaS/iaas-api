"""Cas nominaux et limites de get_share."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.features.shares.service import create_share, get_share
from app.shared.enums import ResourceType
from tests.support import add_project, add_vm, user_id


async def test_member_can_read_share(db, iam):
    """Un membre du projet d'origine consulte le partage."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    row = await create_share(
        db, iam, user_id=uid, project_id="p1", resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    found = await get_share(db, iam, user_id=uid, share_id=row.id)
    assert found.id == row.id


async def test_stranger_and_missing(db, iam):
    """Un tiers est refuse. Un identifiant inconnu est introuvable."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    row = await create_share(
        db, iam, user_id=uid, project_id="p1", resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    stranger = iam.add_user("stranger@x.cm", "pw")
    with pytest.raises(AppError) as exc:
        await get_share(db, iam, user_id=stranger.user_id, share_id=row.id)
    assert exc.value.code == ErrorCode.FORBIDDEN
    with pytest.raises(AppError) as missing:
        await get_share(db, iam, user_id=uid, share_id="inconnu")
    assert missing.value.code == ErrorCode.NOT_FOUND


async def test_guest_needs_the_view_right_on_the_resource_type(db, iam):
    """Un membre du destinataire sans vm.view ne lit pas le partage."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    row = await create_share(
        db, iam, user_id=uid, project_id="p1", resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p2", ["vm.network"])
    with pytest.raises(AppError) as exc:
        await get_share(db, iam, user_id=guest.user_id, share_id=row.id)
    assert exc.value.code == ErrorCode.FORBIDDEN
    await iam.update_rights(guest.user_id, "p2", ["vm.view"])
    found = await get_share(db, iam, user_id=guest.user_id, share_id=row.id)
    assert found.id == row.id
