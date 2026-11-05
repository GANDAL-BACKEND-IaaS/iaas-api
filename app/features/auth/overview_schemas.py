"""Schemas de la vue operationnelle d'un compte pour les administrateurs."""

from pydantic import BaseModel

from app.features.networks.schemas import NetworkOut
from app.features.projects.schemas import InvitationOut
from app.features.requests.schemas import RequestOut
from app.features.shares.schemas import ShareOut
from app.features.vms.schemas import VMOut
from app.shared.enums import MembershipRole
from app.shared.time import UtcDateTime


class UserProjectOverviewOut(BaseModel):
    """Projet lie au compte, avec droits et ressources visibles."""

    id: str
    name: str
    owner_id: str
    role: MembershipRole
    rights: list[str]
    created_at: UtcDateTime
    vms: list[VMOut]
    networks: list[NetworkOut]


class UserOverviewOut(BaseModel):
    """Donnees operationnelles d'un compte, sans recopier son identite IAM."""

    projects: list[UserProjectOverviewOut]
    invitations: list[InvitationOut]
    requests: list[RequestOut]
    shares: list[ShareOut]
