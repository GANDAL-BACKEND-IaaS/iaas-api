"""Schemas du moteur de partages. Creation immediate, sans validation administrateur (R20)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import ResourceType, ShareStatus


class ShareCreateIn(BaseModel):
    """Corps de creation d'un partage vers un projet du meme proprietaire."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"resource_type": "vm", "resource_id": "vm-1", "dest_project_id": "p2"}
            ]
        }
    )

    resource_type: ResourceType
    resource_id: str = Field(min_length=1, max_length=36)
    dest_project_id: str = Field(min_length=1, max_length=36)


class ShareOut(BaseModel):
    """Partage tel que renvoye par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_type: ResourceType
    resource_id: str
    origin_project_id: str
    dest_project_id: str
    created_by: str
    status: ShareStatus
    created_at: datetime
