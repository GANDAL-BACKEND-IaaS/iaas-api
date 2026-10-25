"""Cas nominaux et limites de create_share (F14, R15 a R20)."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.features.shares.service import create_share
from app.shared.enums import ResourceType, ShareStatus
from tests.support import add_project, add_storage, add_vm, own_project, user_id


async def _two_projects(db, iam):
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    return uid


async def test_owner_shares_vm_immediately(db, iam):
    """Le partage devient actif sans appel externe ni validation admin."""
    uid = await _two_projects(db, iam)
    add_vm(db, "p1")
    row = await create_share(
        db, iam, user_id=uid, resource_type=ResourceType.VM, project_id="p1",
        resource_id="vm-1", dest_project_id="p2",
    )
    assert row.status == ShareStatus.ACTIVE.value
    assert row.origin_project_id == "p1"
    assert row.dest_project_id == "p2"


async def test_different_owners_are_forbidden(db, iam):
    """Les deux projets doivent avoir le meme proprietaire."""
    uid = await own_project(db, iam, "p1")
    other = iam.add_user("other@x.cm", "pw")
    await iam.create_project(other.user_id, "p2")
    add_project(db, other.user_id, "p2", "Beta")
    add_vm(db, "p1")
    with pytest.raises(AppError) as exc:
        await create_share(
            db, iam, user_id=uid, resource_type=ResourceType.VM, project_id="p1",
            resource_id="vm-1", dest_project_id="p2",
        )
    assert exc.value.code == ErrorCode.FORBIDDEN


async def test_same_project_is_conflict(db, iam):
    """Le destinataire doit etre un autre projet."""
    uid = await own_project(db, iam)
    add_storage(db, "p1")
    with pytest.raises(AppError) as exc:
        await create_share(
            db, iam, user_id=uid, resource_type=ResourceType.STORAGE, project_id="p1",
            resource_id="st-1", dest_project_id="p1",
        )
    assert exc.value.code == ErrorCode.CONFLICT


async def test_guest_must_have_share_right_and_dest_membership(db, iam):
    """R18 : droit de partage dans l'origine et appartenance au destinataire."""
    owner = await _two_projects(db, iam)
    add_vm(db, "p1")
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p1", ["vm.view"])
    with pytest.raises(AppError) as exc:
        await create_share(
            db, iam, user_id=guest.user_id, resource_type=ResourceType.VM, project_id="p1",
            resource_id="vm-1", dest_project_id="p2",
        )
    assert exc.value.code == ErrorCode.FORBIDDEN
    await iam.invite_user(guest.user_id, "p2", ["vm.view"])
    await iam.update_rights(guest.user_id, "p1", ["vm.share"])
    row = await create_share(
        db, iam, user_id=guest.user_id, resource_type=ResourceType.VM, project_id="p1",
        resource_id="vm-1", dest_project_id="p2",
    )
    assert row.created_by == guest.user_id
    assert owner


async def test_duplicate_active_share_conflicts(db, iam):
    """Un second partage actif vers le meme projet est refuse."""
    uid = await _two_projects(db, iam)
    add_vm(db, "p1")
    await create_share(
        db, iam, user_id=uid, resource_type=ResourceType.VM, project_id="p1",
        resource_id="vm-1", dest_project_id="p2",
    )
    with pytest.raises(AppError) as exc:
        await create_share(
            db, iam, user_id=uid, resource_type=ResourceType.VM, project_id="p1",
            resource_id="vm-1", dest_project_id="p2",
        )
    assert exc.value.code == ErrorCode.CONFLICT


async def test_deleting_resource_cannot_be_shared(db, iam):
    """Une ressource en cours de suppression n'est pas partageable."""
    uid = await _two_projects(db, iam)
    add_vm(db, "p1", state="deleting")
    with pytest.raises(AppError) as exc:
        await create_share(
            db, iam, user_id=uid, resource_type=ResourceType.VM, project_id="p1",
            resource_id="vm-1", dest_project_id="p2",
        )
    assert exc.value.code == ErrorCode.INVALID_STATE
