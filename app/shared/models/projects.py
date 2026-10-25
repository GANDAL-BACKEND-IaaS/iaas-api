"""Modeles lies aux projets : projet, appartenance, invitation (section 4.1).

Le proprietaire est l'utilisateur qui a cree le projet. La propriete ne se transfere pas (R7).
Les droits fins restent portes par le port IAM ; ces tables portent le profil, les droits
additionnels et le cycle de vie. L'IAM est rehydrate depuis ces tables au demarrage.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import Base, new_id
from app.shared.models.rights import ProfileModel
from app.shared.time import utcnow


class Project(Base):
    """Conteneur de ressources IaaS. `owner_id` est la reference IAM du proprietaire."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_project_owner_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    """Lien entre un utilisateur et un projet, avec son role (proprietaire ou invite)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_membership_project_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    additional_rights: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped[ProfileModel | None] = relationship(lazy="selectin")


class Invitation(Base):
    """Proposition de rejoindre un projet. Doit etre acceptee par l'invite (F13)."""

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    inviter_id: Mapped[str] = mapped_column(String(36))
    invitee_id: Mapped[str] = mapped_column(String(36), index=True)
    invitee_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="sent", index=True)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    additional_rights: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(lazy="selectin")
    profile: Mapped[ProfileModel | None] = relationship(lazy="selectin")
