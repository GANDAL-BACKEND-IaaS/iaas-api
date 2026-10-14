"""Modele des machines virtuelles (sections 4.1 et 4.3).

Une VM a un seul projet d'origine. Le partage ne la deplace pas (R17).
Les caracteristiques de base sont RAM, CPU, VRAM et stockage SSD.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base
from app.shared.time import utcnow


class Vm(Base):
    """Machine virtuelle rattachee a son projet d'origine."""

    __tablename__ = "vms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    origin_project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    ram: Mapped[int] = mapped_column()
    cpu: Mapped[int] = mapped_column()
    vram: Mapped[int] = mapped_column()
    ssd: Mapped[int] = mapped_column()
    pack_id: Mapped[int | None] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(16), default="stopped")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
