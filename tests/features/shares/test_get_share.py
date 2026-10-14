"""Cas nominaux et limites de get_share."""

import pytest

from app.application.ports.iam import GlobalRole
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
        db, iam, user_id=uid, resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    found = await get_share(
        db, iam, actor_id=uid, actor_role=GlobalRole.USER, share_id=row.id,
    )
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
        db, iam, user_id=uid, resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    stranger = iam.add_user("stranger@x.cm", "pw")
    with pytest.raises(AppError) as exc:
        await get_share(
            db, iam, actor_id=stranger.user_id, actor_role=GlobalRole.USER, share_id=row.id,
        )
    assert exc.value.code == ErrorCode.FORBIDDEN
    with pytest.raises(AppError) as missing:
        await get_share(
            db, iam, actor_id=uid, actor_role=GlobalRole.USER, share_id=9999,
        )
    assert missing.value.code == ErrorCode.NOT_FOUND
