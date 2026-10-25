"""Modele des demandes de creation ou de modification (section 4.1, cycle 6.1).

Toute demande est liee a un projet (R1) et traitee par un administrateur (R2).
Les etats accepted, refused et cancelled sont finaux, sauf mise a jour d'un pack (R14).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base, new_id
from app.shared.time import utcnow


class ResourceRequest(Base):
    """Requete de creation ou de modification d'une VM ou d'un stockage."""

    __tablename__ = "resource_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    target_resource_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
