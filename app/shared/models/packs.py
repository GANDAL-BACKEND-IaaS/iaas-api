"""Modele des packs de VM, definis par l'administrateur (section 4.4, F17).

Les unites sont explicites et stockees telles quelles : RAM, VRAM et SSD en Go,
CPU en nombre de vCPU.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base, new_id
from app.shared.time import utcnow


class Pack(Base):
    """Configuration preetablie : RAM, vCPU, VRAM et stockage SSD."""

    __tablename__ = "packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    ram_gb: Mapped[int] = mapped_column()
    vcpu: Mapped[int] = mapped_column()
    vram_gb: Mapped[int] = mapped_column()
    ssd_gb: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
