"""Schemas d'entree et de sortie du moteur de demandes.

Chaque route du routeur associe un schema entrant et un schema sortant.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import RequestKind, RequestStatus


class VmCreatePayload(BaseModel):
    """Charge utile d'une demande de creation de VM : pack ou configuration personnalisee (R13)."""

    name: str = Field(min_length=1, max_length=128)
    pack_id: int | None = None
    ram: int | None = Field(default=None, gt=0)
    cpu: int | None = Field(default=None, gt=0)
    vram: int | None = Field(default=None, gt=0)
    ssd: int | None = Field(default=None, gt=0)


class VmUpdatePayload(BaseModel):
    """Charge utile d'une modification des caracteristiques de base d'une VM (F2)."""

    ram: int | None = Field(default=None, gt=0)
    cpu: int | None = Field(default=None, gt=0)
    vram: int | None = Field(default=None, gt=0)
    ssd: int | None = Field(default=None, gt=0)


class StorageCreatePayload(BaseModel):
    """Charge utile d'une demande de creation de stockage : nom et taille (F8)."""

    name: str = Field(min_length=1, max_length=128)
    size: int = Field(gt=0)


class StorageUpdatePayload(BaseModel):
    """Charge utile d'une demande de modification de taille (F9)."""

    size: int = Field(gt=0)


class RequestCreateIn(BaseModel):
    """Corps de depot d'une demande. `payload` est valide selon `kind`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": "p1",
                    "kind": "vm_create",
                    "payload": {"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40},
                }
            ]
        }
    )

    project_id: str = Field(min_length=1, max_length=36)
    kind: RequestKind
    payload: dict
    target_resource_id: str | None = None


class RequestDecisionIn(BaseModel):
    """Decision d'un administrateur. La remarque est optionnelle (R4)."""

    note: str | None = Field(default=None, max_length=2000)


class RequestOut(BaseModel):
    """Demande telle que renvoyee par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    author_id: str
    kind: RequestKind
    status: RequestStatus
    payload: dict
    target_resource_type: str | None
    target_resource_id: str | None
    admin_note: str | None
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
