"""Visibilite d'une ressource dans un projet (section 4.6).

Une ressource est visible dans un projet si ce projet est son projet d'origine,
ou si un partage actif vers ce projet existe.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare


def is_resource_visible(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
    origin_project_id: str,
    project_id: str,
) -> bool:
    """Indique si la ressource est visible dans le projet donne."""
    if origin_project_id == project_id:
        return True
    statement = select(ResourceShare.id).where(
        ResourceShare.resource_type == resource_type,
        ResourceShare.resource_id == resource_id,
        ResourceShare.dest_project_id == project_id,
        ResourceShare.status == ShareStatus.ACTIVE.value,
    )
    return db.scalar(statement) is not None
