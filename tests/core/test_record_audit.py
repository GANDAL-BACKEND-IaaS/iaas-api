"""Cas nominaux et limites du journal d'audit."""

import pytest

from app.core.audit import record_audit
from app.shared.models.audit import AuditLog


def test_record_audit_stores_author_and_action(db):
    """Une ligne horodatee est ajoutee, sans commit impose par le journal."""
    row = record_audit(
        db,
        actor_id="u1",
        action="request.submitted",
        entity_type="request",
        entity_id="1",
        data={"kind": "vm_create"},
    )
    db.commit()
    stored = db.get(AuditLog, row.id)
    assert stored is not None
    assert stored.actor_id == "u1"
    assert stored.action == "request.submitted"
    assert stored.data == {"kind": "vm_create"}
    assert stored.created_at is not None


def test_record_audit_rejects_secrets(db):
    """Un mot de passe ou un jeton ne doit jamais entrer dans le journal."""
    with pytest.raises(ValueError):
        record_audit(
            db,
            actor_id="u1",
            action="login",
            entity_type="user",
            entity_id="u1",
            data={"password": "secret"},
        )
    db.commit()
    assert db.query(AuditLog).count() == 0
