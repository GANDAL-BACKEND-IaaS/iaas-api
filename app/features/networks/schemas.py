"""Schemas reseau."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.time import UtcDateTime


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Le nom ne peut pas etre vide.")
    return value.strip()


class NetworkCreateIn(BaseModel):
    """Creation d'un reseau dans un projet (F7)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "lan-production"}]})

    name: str = Field(min_length=1, max_length=128)

    _trim = field_validator("name")(_not_blank)


class NetworkUpdateIn(BaseModel):
    """Renommage d'un reseau."""

    name: str = Field(min_length=1, max_length=128)

    _trim = field_validator("name")(_not_blank)


class NetworkMembershipIn(BaseModel):
    """VM a rattacher. Elle doit etre visible dans le projet du reseau (R21)."""

    vm_id: str = Field(min_length=1, max_length=36)


class NetworkOut(BaseModel):
    """Reseau et les VMs qu'il relie."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    vm_ids: list[str] = Field(default_factory=list)
    created_at: UtcDateTime
