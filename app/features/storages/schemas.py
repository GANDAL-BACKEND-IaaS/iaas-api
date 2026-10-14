"""Schemas des espaces de stockage. Proprietaire : TABA."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import StorageState


class StorageRequestCreateIn(BaseModel):
    """Demande de creation : nom et taille (F8)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "documents", "size": 100}]})

    name: str = Field(min_length=1, max_length=128)
    size: int = Field(gt=0)


class StorageRequestUpdateIn(BaseModel):
    """Demande de modification de la taille (F9)."""

    size: int = Field(gt=0)


class StorageOut(BaseModel):
    """Espace de stockage renvoye par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_project_id: str
    name: str
    size: int
    state: StorageState
    created_at: datetime
    shared: bool = False


class ShareTargetIn(BaseModel):
    """Projet destinataire d'un partage de stockage (F14)."""

    dest_project_id: str = Field(min_length=1, max_length=36)


class ConfirmIn(BaseModel):
    """Confirmation explicite avant suppression (R6)."""

    confirm: Literal[True]
