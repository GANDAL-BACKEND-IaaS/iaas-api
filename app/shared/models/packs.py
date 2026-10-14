"""Modele des packs de VM, definis par l'administrateur (section 4.4, F17)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base


class Pack(Base):
    """Configuration preetablie : RAM, CPU, VRAM et stockage SSD."""

    __tablename__ = "packs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    ram: Mapped[int] = mapped_column()
    cpu: Mapped[int] = mapped_column()
    vram: Mapped[int] = mapped_column()
    ssd: Mapped[int] = mapped_column()
