"""Cas nominaux et limites de get_request et list_requests."""

import pytest

from app.application.ports.iam import GlobalRole
from app.core.errors import AppError, ErrorCode
from app.features.requests.service import get_request, submit_request
from app.shared.enums import RequestKind
from tests.support import own_project, user_id

_CUSTOM = {"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}


async def test_author_and_admin_can_read(db, iam):
    """L'auteur et l'administrateur lisent la demande. Un tiers non."""
    uid = await own_project(db, iam)
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    found = get_request(db, actor_id=uid, actor_role=GlobalRole.USER, request_id=row.id)
    assert found.id == row.id
    admin = await user_id(iam, "root@x.cm")
    assert get_request(db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id).id == row.id
    other = iam.add_user("other@x.cm", "pw")
    with pytest.raises(AppError) as exc:
        get_request(db, actor_id=other.user_id, actor_role=GlobalRole.USER, request_id=row.id)
    assert exc.value.code == ErrorCode.FORBIDDEN


def test_unknown_request(db):
    """Une demande absente est introuvable, y compris pour un admin."""
    with pytest.raises(AppError) as exc:
        get_request(db, actor_id="root", actor_role=GlobalRole.ADMIN, request_id=404)
    assert exc.value.code == ErrorCode.NOT_FOUND
