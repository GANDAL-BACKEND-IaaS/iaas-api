"""Cas nominaux et limites de submit_request."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.features.requests.service import submit_request
from app.shared.enums import RequestKind, RequestStatus
from app.shared.models.packs import Pack
from tests.support import add_storage, add_vm, own_project

_CUSTOM = {"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}


async def test_submit_custom_vm_is_pending(db, iam):
    """Une configuration personnalisee complete cree une demande en attente."""
    uid = await own_project(db, iam)
    row = await submit_request(
        db,
        iam,
        author_id=uid,
        project_id="p1",
        kind=RequestKind.VM_CREATE,
        payload=_CUSTOM,
        target_resource_id=None,
    )
    assert row.status == RequestStatus.PENDING.value
    assert row.payload["ram"] == 2048
    assert row.payload["pack_id"] is None


async def test_submit_pack_copies_pack_values(db, iam):
    """Choisir un pack fige les caracteristiques du pack dans la demande."""
    uid = await own_project(db, iam)
    pack = Pack(name="Standard", ram=1024, cpu=1, vram=64, ssd=20)
    db.add(pack)
    db.commit()
    row = await submit_request(
        db,
        iam,
        author_id=uid,
        project_id="p1",
        kind=RequestKind.VM_CREATE,
        payload={"name": "web", "pack_id": pack.id},
        target_resource_id=None,
    )
    assert row.payload["ram"] == 1024
    assert row.payload["pack_id"] == pack.id


async def test_submit_rejects_pack_and_custom_together(db, iam):
    """R13 : pack ou configuration personnalisee, pas les deux."""
    uid = await own_project(db, iam)
    pack = Pack(name="Standard", ram=1024, cpu=1, vram=64, ssd=20)
    db.add(pack)
    db.commit()
    payload = {**_CUSTOM, "pack_id": pack.id}
    with pytest.raises(AppError) as exc:
        await submit_request(
            db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
            payload=payload, target_resource_id=None,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


async def test_submit_rejects_incomplete_custom(db, iam):
    """Une configuration personnalisee incomplète est refusee."""
    uid = await own_project(db, iam)
    with pytest.raises(AppError) as exc:
        await submit_request(
            db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
            payload={"name": "web", "ram": 1}, target_resource_id=None,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


async def test_submit_unknown_pack_is_not_found(db, iam):
    """Un pack inconnu n'enregistre pas de demande."""
    uid = await own_project(db, iam)
    with pytest.raises(AppError) as exc:
        await submit_request(
            db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
            payload={"name": "web", "pack_id": 999}, target_resource_id=None,
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


async def test_submit_without_membership_is_forbidden(db, iam):
    """R1 et figure 3 : pas de demande hors d'un projet dont on est membre."""
    outsider = iam.add_user("out@x.cm", "pw")
    await own_project(db, iam)
    with pytest.raises(AppError) as exc:
        await submit_request(
            db, iam, author_id=outsider.user_id, project_id="p1", kind=RequestKind.VM_CREATE,
            payload=_CUSTOM, target_resource_id=None,
        )
    assert exc.value.code == ErrorCode.FORBIDDEN


async def test_submit_storage_update_requires_target(db, iam):
    """Une modification sans ressource cible est invalide."""
    uid = await own_project(db, iam)
    with pytest.raises(AppError) as exc:
        await submit_request(
            db, iam, author_id=uid, project_id="p1", kind=RequestKind.STORAGE_UPDATE,
            payload={"size": 10}, target_resource_id=None,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


async def test_submit_update_on_visible_vm(db, iam):
    """F2 : une modification de VM visible est enregistree."""
    uid = await own_project(db, iam)
    add_vm(db, "p1")
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_UPDATE,
        payload={"ram": 4096}, target_resource_id="vm-1",
    )
    assert row.target_resource_id == "vm-1"
    assert row.payload["ram"] == 4096


async def test_submit_rejects_deleting_storage(db, iam):
    """Une ressource en cours de suppression ne peut pas etre modifiee."""
    uid = await own_project(db, iam)
    add_storage(db, "p1", state="deleting")
    with pytest.raises(AppError) as exc:
        await submit_request(
            db, iam, author_id=uid, project_id="p1", kind=RequestKind.STORAGE_UPDATE,
            payload={"size": 10}, target_resource_id="st-1",
        )
    assert exc.value.code == ErrorCode.INVALID_STATE
