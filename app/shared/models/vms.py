"""Modele des machines virtuelles (sections 4.1 et 4.3).

Une VM a un seul projet d'origine. Le partage ne la deplace pas (R17).
L'adresse IP est un attribut de premiere classe, comme les caracteristiques en Go.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base, new_id
from app.shared.time import utcnow


class Vm(Base):
    """Machine virtuelle rattachee a son projet d'origine."""

    __tablename__ = "vms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    origin_project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    ram_gb: Mapped[int] = mapped_column()
    vcpu: Mapped[int] = mapped_column()
    vram_gb: Mapped[int] = mapped_column()
    ssd_gb: Mapped[int] = mapped_column()
    pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("packs.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(16), default="stopped")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
