"""Modele des partages de ressources entre projets (section 4.6, cycle 6.3).

Un partage rend une ressource visible dans un projet destinataire. Il ne transmet aucun droit (R16).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base, new_id
from app.shared.time import utcnow


class ResourceShare(Base):
    """Lien de visibilite entre une ressource et un projet destinataire."""

    __tablename__ = "resource_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_type: Mapped[str] = mapped_column(String(16))
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    origin_project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dest_project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
