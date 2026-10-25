"""Modele des espaces de stockage de type S3 (section 4.5).

Les caracteristiques de base sont le nom, la taille en Go et l'adresse IP.
Un stockage n'est jamais mis en reseau (R22).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base, new_id
from app.shared.time import utcnow


class Storage(Base):
    """Espace de stockage rattache a son projet d'origine."""

    __tablename__ = "storages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    origin_project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    size_gb: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(16), default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
