"""Cas nominaux et limites de authorize (figure 3)."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare
from app.shared.policies.access import ResourceView, authorize
from tests.support import add_vm, own_project, user_id


async def test_owner_is_allowed(db, iam):
    """Le proprietaire possede tous les droits."""
    uid = await own_project(db, iam)
    add_vm(db, "p1")
    await authorize(
        iam=iam,
        db=db,
        user_id=uid,
        project_id="p1",
        required_right="vm.delete",
        resource=ResourceView("vm", "vm-1", "p1"),
    )


async def test_non_member_is_forbidden(db, iam):
    """Un utilisateur hors du projet est refuse, meme si la ressource existe."""
    await own_project(db, iam)
    outsider = iam.add_user("out@x.cm", "pw")
    add_vm(db, "p1")
    with pytest.raises(AppError) as exc:
        await authorize(
            iam=iam,
            db=db,
            user_id=outsider.user_id,
            project_id="p1",
            required_right="vm.view",
            resource=ResourceView("vm", "vm-1", "p1"),
        )
    assert exc.value.code == ErrorCode.FORBIDDEN


async def test_member_without_right_is_forbidden(db, iam):
    """Un invite sans le droit requis est refuse."""
    owner = await own_project(db, iam)
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p1", ["storage.view"])
    add_vm(db, "p1")
    with pytest.raises(AppError) as exc:
        await authorize(
            iam=iam,
            db=db,
            user_id=guest.user_id,
            project_id="p1",
            required_right="vm.view",
            resource=ResourceView("vm", "vm-1", "p1"),
        )
    assert exc.value.code == ErrorCode.FORBIDDEN
    assert owner


async def test_active_share_grants_visibility(db, iam):
    """Une VM partagee est accessible avec les droits du projet destinataire."""
    owner = await user_id(iam)
    await iam.create_project(owner, "p1")
    await iam.create_project(owner, "p2")
    from tests.support import add_project

    add_project(db, owner, "p1")
    add_project(db, owner, "p2")
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p2", ["vm.view"])
    add_vm(db, "p1")
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by=owner,
            status=ShareStatus.ACTIVE.value,
        )
    )
    db.commit()
    await authorize(
        iam=iam,
        db=db,
        user_id=guest.user_id,
        project_id="p2",
        required_right="vm.view",
        resource=ResourceView("vm", "vm-1", "p1"),
    )


async def test_revoked_share_hides_resource(db, iam):
    """Un partage revoque ne rend plus la ressource visible."""
    owner = await user_id(iam)
    await iam.create_project(owner, "p1")
    await iam.create_project(owner, "p2")
    from tests.support import add_project

    add_project(db, owner, "p1")
    add_project(db, owner, "p2")
    add_vm(db, "p1")
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by=owner,
            status=ShareStatus.REVOKED.value,
        )
    )
    db.commit()
    with pytest.raises(AppError) as exc:
        await authorize(
            iam=iam,
            db=db,
            user_id=owner,
            project_id="p2",
            required_right="vm.view",
            resource=ResourceView("vm", "vm-1", "p1"),
        )
    assert exc.value.code == ErrorCode.FORBIDDEN
