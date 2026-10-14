"""Schemas VM et packs. Proprietaire : NAOMI."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import PowerAction, VmState


class VmRequestCreateIn(BaseModel):
    """Demande de creation de VM : pack ou configuration personnalisee (F1, R13)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}]
        }
    )

    name: str = Field(min_length=1, max_length=128)
    pack_id: int | None = None
    ram: int | None = Field(default=None, gt=0)
    cpu: int | None = Field(default=None, gt=0)
    vram: int | None = Field(default=None, gt=0)
    ssd: int | None = Field(default=None, gt=0)


class VmRequestUpdateIn(BaseModel):
    """Demande de modification des caracteristiques de base (F2)."""

    ram: int | None = Field(default=None, gt=0)
    cpu: int | None = Field(default=None, gt=0)
    vram: int | None = Field(default=None, gt=0)
    ssd: int | None = Field(default=None, gt=0)


class VmOut(BaseModel):
    """VM renvoyee par l'API, y compris son etat connu."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_project_id: str
    name: str
    ram: int
    cpu: int
    vram: int
    ssd: int
    pack_id: int | None
    state: VmState
    created_at: datetime
    shared: bool = False


class PowerIn(BaseModel):
    """Action directe d'alimentation (F4)."""

    action: PowerAction


class ConsoleOut(BaseModel):
    """Acces a la console fourni par les groupes infrastructure (F5)."""

    url: str
    expires_in: int


class ShareTargetIn(BaseModel):
    """Projet destinataire d'un partage de VM (F14)."""

    dest_project_id: str = Field(min_length=1, max_length=36)


class ConfirmIn(BaseModel):
    """Confirmation explicite avant suppression (R6)."""

    confirm: Literal[True]
