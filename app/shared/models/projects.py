"""Modeles lies aux projets : projet, appartenance, invitation (section 4.1).

Le proprietaire est l'utilisateur qui a cree le projet. La propriete ne se transfere pas (R7).
Les droits fins restent portes par le port IAM ; ces tables portent le cycle de vie et le nom.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base
from app.shared.time import utcnow


class Project(Base):
    """Conteneur de ressources IaaS. `owner_id` est la reference IAM du proprietaire."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    """Lien entre un utilisateur et un projet, avec son role (proprietaire ou invite)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_membership_project_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MembershipRight(Base):
    """Droit accorde a une appartenance. Vaut pour toutes les ressources du type (R10)."""

    __tablename__ = "membership_rights"

    membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True
    )
    right_code: Mapped[str] = mapped_column(
        ForeignKey("rights.code", ondelete="CASCADE"), primary_key=True
    )


class Invitation(Base):
    """Proposition de rejoindre un projet. Doit etre acceptee par l'invite (F13)."""

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    inviter_id: Mapped[str] = mapped_column(String(36))
    invitee_email: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="sent", index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    rights_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
