"""Cas nominaux et limites de la visibilite d'une ressource."""

from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare
from app.shared.policies.visibility import is_resource_visible
from tests.support import add_project, add_vm


def test_origin_project_is_visible(db):
    """Le projet d'origine voit toujours la ressource, sans partage."""
    add_project(db, "u", "p1")
    add_vm(db, "p1")
    assert is_resource_visible(
        db, resource_type="vm", resource_id="vm-1", origin_project_id="p1", project_id="p1"
    )


def test_active_share_makes_dest_visible(db):
    """Un partage actif rend la ressource visible dans le projet destinataire."""
    add_project(db, "u", "p1")
    add_project(db, "u", "p2")
    add_vm(db, "p1")
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by="u",
            status=ShareStatus.ACTIVE.value,
        )
    )
    db.commit()
    assert is_resource_visible(
        db, resource_type="vm", resource_id="vm-1", origin_project_id="p1", project_id="p2"
    )


def test_revoked_or_other_project_is_hidden(db):
    """Un partage revoque ou un autre projet ne donnent pas la visibilite."""
    add_project(db, "u", "p1")
    add_project(db, "u", "p2")
    add_vm(db, "p1")
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by="u",
            status=ShareStatus.REVOKED.value,
        )
    )
    db.commit()
    assert not is_resource_visible(
        db, resource_type="vm", resource_id="vm-1", origin_project_id="p1", project_id="p2"
    )
    assert not is_resource_visible(
        db, resource_type="vm", resource_id="vm-1", origin_project_id="p1", project_id="p3"
    )
