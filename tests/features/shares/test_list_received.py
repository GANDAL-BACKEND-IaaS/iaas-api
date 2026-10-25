"""Cas nominaux et limites de la liste des partages recus (F14, R12)."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.core.pagination import PageParams
from app.features.shares.service import create_share, list_received
from app.shared.enums import ResourceType
from tests.support import add_project, add_storage, add_vm, user_id


async def _shared_projects(db, iam, guest_rights):
    owner = await user_id(iam)
    await iam.create_project(owner, "p1")
    await iam.create_project(owner, "p2")
    add_project(db, owner, "p1")
    add_project(db, owner, "p2")
    add_vm(db, "p1")
    add_storage(db, "p1")
    await create_share(
        db,
        iam,
        user_id=owner,
        project_id="p1",
        resource_type=ResourceType.VM,
        resource_id="vm-1",
        dest_project_id="p2",
    )
    await create_share(
        db,
        iam,
        user_id=owner,
        project_id="p1",
        resource_type=ResourceType.STORAGE,
        resource_id="st-1",
        dest_project_id="p2",
    )
    guest = iam.add_user("guest@x.cm", "pw")
    if guest_rights:
        await iam.invite_user(guest.user_id, "p2", guest_rights)
    return guest


async def test_vm_view_only_lists_vm_shares(db, iam):
    """Seuls les partages du type autorise sont retournes."""
    guest = await _shared_projects(db, iam, ["vm.view"])
    rows, total = await list_received(
        db, iam, user_id=guest.user_id, project_id="p2", params=PageParams()
    )
    assert total == 1
    assert rows[0].resource_type == ResourceType.VM.value


async def test_storage_view_only_lists_storage_shares(db, iam):
    """storage.view ne donne pas acces aux partages de VM."""
    guest = await _shared_projects(db, iam, ["storage.view"])
    rows, total = await list_received(
        db, iam, user_id=guest.user_id, project_id="p2", params=PageParams()
    )
    assert total == 1
    assert rows[0].resource_type == ResourceType.STORAGE.value


async def test_without_view_right_listing_is_forbidden(db, iam):
    """Un membre sans droit de lecture ne liste pas les partages recus."""
    guest = await _shared_projects(db, iam, ["vm.network"])
    with pytest.raises(AppError) as exc:
        await list_received(
            db, iam, user_id=guest.user_id, project_id="p2", params=PageParams()
        )
    assert exc.value.code == ErrorCode.FORBIDDEN
