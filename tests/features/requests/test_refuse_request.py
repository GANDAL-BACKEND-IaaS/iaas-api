"""Cas nominaux et limites de refuse_request (F16, R4)."""

import pytest

from app.application.ports.iam import GlobalRole
from app.core.errors import AppError, ErrorCode
from app.features.requests.service import refuse_request, submit_request
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.shared.enums import RequestKind, RequestStatus
from tests.support import own_project, user_id

_CUSTOM = {"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}


async def test_admin_refuses_with_optional_note(db, iam):
    """Le refus n'exige pas de remarque et notifie l'auteur."""
    uid = await own_project(db, iam)
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.STORAGE_CREATE,
        payload={"name": "docs", "size": 10}, target_resource_id=None,
    )
    admin = await user_id(iam, "root@x.cm")
    notes = FakeNotifications()
    refused = await refuse_request(
        db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id,
        note=None, notifications=notes,
    )
    assert refused.status == RequestStatus.REFUSED.value
    assert refused.admin_note is None
    assert notes.sent


async def test_cannot_refuse_cancelled(db, iam):
    """Une demande qui n'est plus en attente ne se refuse pas."""
    from app.features.requests.service import cancel_request

    uid = await own_project(db, iam)
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    cancel_request(db, author_id=uid, request_id=row.id)
    admin = await user_id(iam, "root@x.cm")
    with pytest.raises(AppError) as exc:
        await refuse_request(
            db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id,
            note="trop tard", notifications=FakeNotifications(),
        )
    assert exc.value.code == ErrorCode.INVALID_STATE
