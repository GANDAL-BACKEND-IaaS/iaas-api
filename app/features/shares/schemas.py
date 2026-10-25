"""Schemas du moteur de partages. Creation immediate, sans validation administrateur (R20)."""

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import ResourceType, ShareStatus
from app.shared.time import UtcDateTime


class ShareCreateIn(BaseModel):
    """Projet destinataire d'un partage d'une ressource identifiee par la route."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"dest_project_id": "prj-beta"}]})

    dest_project_id: str = Field(min_length=1, max_length=36)


class ShareOut(BaseModel):
    """Partage tel que renvoye par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    resource_type: ResourceType
    resource_id: str
    origin_project_id: str
    dest_project_id: str
    created_by: str
    status: ShareStatus
    created_at: UtcDateTime


class ShareRevokeOut(BaseModel):
    """Reponse de la revocation : partage mis a jour et message lisible."""

    share: ShareOut
    message: str
