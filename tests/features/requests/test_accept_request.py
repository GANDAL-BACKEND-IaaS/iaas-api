"""Cas nominaux et limites de accept_request (F16, R3)."""

import pytest

from app.application.ports.iam import GlobalRole
from app.core.errors import AppError, ErrorCode
from app.features.requests.service import (
    RequestContext,
    accept_request,
    clear_handlers,
    register_default_handlers,
    register_handler,
    submit_request,
)
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.infrastructure.storage.fake_storage import FakeStorage
from app.shared.enums import RequestKind, RequestStatus
from app.shared.models.requests import ResourceRequest
from app.shared.models.vms import Vm
from tests.support import own_project, user_id

_CUSTOM = {"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}


async def _pending(db, iam):
    uid = await own_project(db, iam)
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    return uid, row


async def test_admin_accept_creates_vm(db, iam):
    """L'acceptation cree la VM via le port et notifie l'auteur."""
    _, row = await _pending(db, iam)
    admin = await user_id(iam, "root@x.cm")
    hypervisor = FakeHypervisor()
    notes = FakeNotifications()
    accepted = await accept_request(
        db,
        actor_id=admin,
        actor_role=GlobalRole.ADMIN,
        request_id=row.id,
        note="ok",
        hypervisor=hypervisor,
        storage=FakeStorage(),
        notifications=notes,
    )
    assert accepted.status == RequestStatus.ACCEPTED.value
    assert accepted.admin_note == "ok"
    assert db.query(Vm).count() == 1
    assert len(hypervisor.vms) == 1
    assert notes.sent[0].user_id == accepted.author_id


async def test_user_cannot_accept(db, iam):
    """Un utilisateur simple ne traite pas les demandes."""
    uid, row = await _pending(db, iam)
    with pytest.raises(AppError) as exc:
        await accept_request(
            db, actor_id=uid, actor_role=GlobalRole.USER, request_id=row.id, note=None,
            hypervisor=FakeHypervisor(), storage=FakeStorage(), notifications=FakeNotifications(),
        )
    assert exc.value.code == ErrorCode.FORBIDDEN


async def test_missing_handler_does_not_accept(db, iam):
    """Sans handler, la demande reste en attente."""
    _, row = await _pending(db, iam)
    admin = await user_id(iam, "root@x.cm")
    clear_handlers()
    try:
        with pytest.raises(AppError) as exc:
            await accept_request(
                db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id, note=None,
                hypervisor=FakeHypervisor(), storage=FakeStorage(), notifications=FakeNotifications(),
            )
        assert exc.value.code == ErrorCode.NOT_IMPLEMENTED
    finally:
        register_default_handlers()
    assert db.get(ResourceRequest, row.id).status == RequestStatus.PENDING.value


async def test_upstream_failure_rolls_back(db, iam):
    """Si l'hyperviseur est indisponible, rien n'est accepte."""
    _, row = await _pending(db, iam)
    admin = await user_id(iam, "root@x.cm")

    async def boom(context: RequestContext) -> None:
        context.request.payload = {"mutated": True}
        raise AppError(ErrorCode.UPSTREAM_UNAVAILABLE, "down")

    register_handler(RequestKind.VM_CREATE, boom)
    try:
        with pytest.raises(AppError) as exc:
            await accept_request(
                db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id, note=None,
                hypervisor=FakeHypervisor(), storage=FakeStorage(), notifications=FakeNotifications(),
            )
        assert exc.value.code == ErrorCode.UPSTREAM_UNAVAILABLE
    finally:
        register_default_handlers()
    stored = db.get(ResourceRequest, row.id)
    assert stored.status == RequestStatus.PENDING.value
    assert stored.payload["name"] == "web"


async def test_cannot_accept_twice(db, iam):
    """Un etat final ne peut plus etre accepte."""
    _, row = await _pending(db, iam)
    admin = await user_id(iam, "root@x.cm")
    await accept_request(
        db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id, note=None,
        hypervisor=FakeHypervisor(), storage=FakeStorage(), notifications=FakeNotifications(),
    )
    with pytest.raises(AppError) as exc:
        await accept_request(
            db, actor_id=admin, actor_role=GlobalRole.ADMIN, request_id=row.id, note=None,
            hypervisor=FakeHypervisor(), storage=FakeStorage(), notifications=FakeNotifications(),
        )
    assert exc.value.code == ErrorCode.INVALID_STATE
