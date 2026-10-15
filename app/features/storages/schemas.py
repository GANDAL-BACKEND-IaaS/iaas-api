"""Schemas des espaces de stockage. Proprietaire : TABA."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.shared.enums import StorageState


class StorageRequestCreateIn(BaseModel):
    """Demande de creation : nom et taille en Go (F8)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "documents", "size": 100}]})

    # Espaces retires avant le controle de longueur : un nom fait d'espaces est refuse.
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    size: int = Field(gt=0, description="Taille en Go, strictement positive.")


class StorageRequestUpdateIn(BaseModel):
    """Demande de modification : seule la taille change (F9)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"size": 200}]})

    size: int = Field(gt=0, description="Nouvelle taille en Go, strictement positive.")


class StorageOut(BaseModel):
    """Espace de stockage vu depuis un projet. `shared` est vrai s'il y est partage."""

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

    model_config = ConfigDict(json_schema_extra={"examples": [{"dest_project_id": "p2"}]})

    dest_project_id: str = Field(min_length=1, max_length=36)


class ConfirmIn(BaseModel):
    """Confirmation de suppression (R6). Sans `confirm: true`, l'API renvoie l'avertissement."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"confirm": True}]})

    confirm: bool = False
