from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import Base, new_id

profile_rights = Table(
    "profile_rights",
    Base.metadata,
    Column("profile_id", ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("right_code", ForeignKey("rights.code", ondelete="CASCADE"), primary_key=True),
)


class RightModel(Base):
    """Droit existant sur la plateforme (catalogue)."""

    __tablename__ = "rights"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class ProfileModel(Base):
    """Profil de droits, personnalisable par l'administrateur."""

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    rights: Mapped[list[RightModel]] = relationship(secondary=profile_rights, lazy="selectin")
