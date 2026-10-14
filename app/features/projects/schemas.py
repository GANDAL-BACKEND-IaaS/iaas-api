"""Schemas des projets, membres et invitations. Proprietaire du dossier : ZUCHUON."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import InvitationStatus, MembershipRole


class ProjectCreateIn(BaseModel):
    """Corps de creation d'un projet (F12)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Projet Alpha"}]})

    name: str = Field(min_length=1, max_length=128)


class ProjectUpdateIn(BaseModel):
    """Corps de renommage d'un projet. Reserve au proprietaire."""

    name: str = Field(min_length=1, max_length=128)


class ProjectOut(BaseModel):
    """Projet renvoye par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    owner_id: str
    created_at: datetime


class MemberOut(BaseModel):
    """Membre d'un projet et ses droits."""

    user_id: str
    role: MembershipRole
    rights: list[str]


class InvitationCreateIn(BaseModel):
    """Invitation : profil et droits a la carte, plafonnes a ceux de l'invitant (R8)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"invitee_email": "bob@iaas.cm", "profile_id": 1, "extra_rights": []}]
        }
    )

    invitee_email: str = Field(min_length=3, max_length=255)
    profile_id: int | None = None
    extra_rights: list[str] = Field(default_factory=list)


class InvitationOut(BaseModel):
    """Invitation et son etat."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    inviter_id: str
    invitee_email: str
    status: InvitationStatus
    profile_id: int | None
    rights_snapshot: list[str]
    created_at: datetime


class ConfirmIn(BaseModel):
    """Confirmation explicite exigee avant une suppression (R6, R23)."""

    confirm: Literal[True] = Field(description="Doit valoir true pour confirmer.")
