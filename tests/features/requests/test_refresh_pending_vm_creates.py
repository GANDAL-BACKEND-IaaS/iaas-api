"""Cas nominaux et limites de refresh_pending_vm_creates (R14)."""

from app.features.requests.service import refresh_pending_vm_creates, submit_request
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.shared.enums import RequestKind, RequestStatus
from app.shared.models.requests import ResourceRequest
from tests.support import add_pack, own_project


async def test_pending_pack_requests_are_updated_and_stay_pending(db, iam):
    """Modifier un pack met a jour les demandes en attente et les laisse a valider."""
    uid = await own_project(db, iam)
    pack = add_pack(db, "Standard", ram_gb=1, vcpu=1, vram_gb=1, ssd_gb=20)
    pending = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload={"name": "web", "pack_id": pack.id}, target_resource_id=None,
    )
    custom = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload={
            "name": "autre",
            "configuration": {"ram_gb": 1, "vcpu": 1, "vram_gb": 1, "ssd_gb": 1},
        },
        target_resource_id=None,
    )
    pack.ram_gb = 8
    notes = FakeNotifications()
    touched = await refresh_pending_vm_creates(
        db, actor_id="admin", pack=pack, notifications=notes,
    )
    assert [row.id for row in touched] == [pending.id]
    refreshed = db.get(ResourceRequest, pending.id)
    assert refreshed.payload["ram_gb"] == 8
    assert refreshed.status == RequestStatus.PENDING.value
    assert db.get(ResourceRequest, custom.id).payload["configuration"]["ram_gb"] == 1
    assert notes.sent[0].user_id == uid


async def test_accepted_request_is_not_refreshed(db, iam):
    """Les VM deja creees, donc les demandes acceptees, ne sont pas modifiees."""
    uid = await own_project(db, iam)
    pack = add_pack(db, "Standard", ram_gb=1, vcpu=1, vram_gb=1, ssd_gb=20)
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload={"name": "web", "pack_id": pack.id}, target_resource_id=None,
    )
    row.status = RequestStatus.ACCEPTED.value
    db.commit()
    pack.ram_gb = 9
    touched = await refresh_pending_vm_creates(
        db, actor_id="admin", pack=pack, notifications=FakeNotifications(),
    )
    assert touched == []
    assert db.get(ResourceRequest, row.id).payload["ram_gb"] == 1
