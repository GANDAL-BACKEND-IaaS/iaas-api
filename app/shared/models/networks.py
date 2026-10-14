"""Modele des reseaux de VMs au sein d'un projet (section 4.1, F7).

Un reseau est defini dans un projet et ne relie que des VMs visibles dans ce projet (R21).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base
from app.shared.time import utcnow


class Network(Base):
    """Regroupement de VMs mises en reseau dans un projet."""

    __tablename__ = "networks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NetworkVm(Base):
    """Lien entre un reseau et une VM visible dans le projet de ce reseau."""

    __tablename__ = "network_vms"
    __table_args__ = (UniqueConstraint("network_id", "vm_id", name="uq_network_vm"),)

    network_id: Mapped[str] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"), primary_key=True)
    vm_id: Mapped[str] = mapped_column(ForeignKey("vms.id", ondelete="CASCADE"), primary_key=True)
