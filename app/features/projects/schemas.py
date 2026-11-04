"""Schemas des projets, membres et invitations."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.enums import InvitationStatus, MembershipRole
from app.shared.time import UtcDateTime


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Le nom ne peut pas etre vide.")
    return value.strip()


def _normalize_invitee_id(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("L'identifiant de l'invite ne peut pas etre vide.")
    return value


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    local, separator, domain = value.partition("@")
    if not separator or not local or not domain or any(char.isspace() for char in value):
        raise ValueError("Adresse email invalide.")
    return value


class ProjectCreateIn(BaseModel):
    """Corps de creation d'un projet (F12)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Projet Alpha"}]})

    name: str = Field(min_length=1, max_length=128)

    _trim = field_validator("name")(_not_blank)


class ProjectUpdateIn(BaseModel):
    """Corps de renommage d'un projet. Reserve au proprietaire."""

    name: str = Field(min_length=1, max_length=128)

    _trim = field_validator("name")(_not_blank)


class ProjectOut(BaseModel):
    """Projet renvoye par l'API, avec le role de l'utilisateur courant."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    owner_id: str
    current_user_role: MembershipRole
    created_at: UtcDateTime


class ProjectMemberOut(BaseModel):
    """Membre d'un projet : profil, droits effectifs et date d'entree."""

    user_id: str
    role: MembershipRole
    profile_id: str | None
    rights: list[str]
    joined_at: UtcDateTime


class MemberRightsUpdateIn(BaseModel):
    """Modification des droits d'un invite. Champs omis = inchanges."""

    profile_id: str | None = None
    additional_rights: list[str] | None = None


class InvitationCreateIn(BaseModel):
    """Invitation : identifiant IAM ou email, avec profil et droits a la carte (R8)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "bob@iaas.cm",
                    "profile_id": "prof-lecteur",
                    "additional_rights": ["vm.request_create"],
                },
                {
                    "invitee_id": "usr-bob",
                    "profile_id": "prof-lecteur",
                    "additional_rights": ["vm.request_create"],
                },
            ]
        }
    )

    invitee_id: str | None = Field(default=None, min_length=1, max_length=36)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    profile_id: str | None = None
    additional_rights: list[str] = Field(default_factory=list)

    _trim_invitee_id = field_validator("invitee_id")(_normalize_invitee_id)
    _clean_email = field_validator("email")(_normalize_email)

    @model_validator(mode="after")
    def _require_one_identifier(self) -> "InvitationCreateIn":
        if (self.invitee_id is None) == (self.email is None):
            raise ValueError("Fournir soit invitee_id, soit email, mais pas les deux.")
        return self


class InvitationOut(BaseModel):
    """Invitation et son etat."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    project_name: str
    inviter_id: str
    invitee_id: str
    invitee_email: str | None
    status: InvitationStatus
    profile_id: str | None
    additional_rights: list[str]
    created_at: UtcDateTime
    updated_at: UtcDateTime
