"""Cas nominaux et limites de cancel_request (F15, R5)."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.features.requests.service import cancel_request, submit_request
from app.shared.enums import RequestKind, RequestStatus
from tests.support import own_project

_CUSTOM = {"name": "web", "configuration": {"ram_gb": 2, "vcpu": 2, "vram_gb": 1, "ssd_gb": 40}}


async def _pending(db, iam):
    uid = await own_project(db, iam)
    row = await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    return uid, row


async def test_author_cancels_pending(db, iam):
    """L'auteur annule une demande en attente."""
    uid, row = await _pending(db, iam)
    cancelled = cancel_request(db, author_id=uid, request_id=row.id)
    assert cancelled.status == RequestStatus.CANCELLED.value


async def test_other_user_cannot_cancel(db, iam):
    """Un autre utilisateur ne peut pas annuler la demande."""
    _, row = await _pending(db, iam)
    other = iam.add_user("other@x.cm", "pw")
    with pytest.raises(AppError) as exc:
        cancel_request(db, author_id=other.user_id, request_id=row.id)
    assert exc.value.code == ErrorCode.FORBIDDEN


async def test_cannot_cancel_twice(db, iam):
    """Une demande deja annulee n'est plus annulable."""
    uid, row = await _pending(db, iam)
    cancel_request(db, author_id=uid, request_id=row.id)
    with pytest.raises(AppError) as exc:
        cancel_request(db, author_id=uid, request_id=row.id)
    assert exc.value.code == ErrorCode.INVALID_STATE


def test_unknown_request_is_not_found(db):
    """Une demande absente repond introuvable."""
    with pytest.raises(AppError) as exc:
        cancel_request(db, author_id="nobody", request_id="inconnu")
    assert exc.value.code == ErrorCode.NOT_FOUND
