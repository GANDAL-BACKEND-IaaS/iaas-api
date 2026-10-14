"""Cas nominaux et limites de refresh_pending_vm_creates (R14)."""

from app.features.requests.service import refresh_pending_vm_creates, submit_request
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.shared.enums import RequestKind, RequestStatus
from app.shared.models.packs import Pack
from app.shared.models.requests import ResourceRequest
from tests.support import own_project


async def test_pending_pack_requests_are_updated_and_stay_pending(db, iam):
    """Modifier un pack met a jour les demandes en attente et les laisse a valider."""
    uid = await own_project(db, iam)
    pack = Pack(name="Standard", ram=1024, cpu=1, vram=64, ssd=20)
    db.add(pack)
    db.commit()
    pending = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload={"name": "web", "pack_id": pack.id}, target_resource_id=None,
    )
    custom = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload={"name": "autre", "ram": 1, "cpu": 1, "vram": 1, "ssd": 1},
        target_resource_id=None,
    )
    pack.ram = 8192
    notes = FakeNotifications()
    touched = await refresh_pending_vm_creates(
        db, actor_id="admin", pack=pack, notifications=notes,
    )
    assert [row.id for row in touched] == [pending.id]
    refreshed = db.get(ResourceRequest, pending.id)
    assert refreshed.payload["ram"] == 8192
    assert refreshed.status == RequestStatus.PENDING.value
    assert db.get(ResourceRequest, custom.id).payload["ram"] == 1
    assert notes.sent[0].user_id == uid


async def test_accepted_request_is_not_refreshed(db, iam):
    """Les VM deja creees, donc les demandes acceptees, ne sont pas modifiees."""
    uid = await own_project(db, iam)
    pack = Pack(name="Standard", ram=1024, cpu=1, vram=64, ssd=20)
    db.add(pack)
    db.commit()
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload={"name": "web", "pack_id": pack.id}, target_resource_id=None,
    )
    row.status = RequestStatus.ACCEPTED.value
    db.commit()
    pack.ram = 999
    touched = await refresh_pending_vm_creates(
        db, actor_id="admin", pack=pack, notifications=FakeNotifications(),
    )
    assert touched == []
    assert db.get(ResourceRequest, row.id).payload["ram"] == 1024
