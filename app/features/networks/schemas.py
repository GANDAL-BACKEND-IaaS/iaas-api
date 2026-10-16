"""Schemas reseau. Proprietaire : KOM."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NetworkCreateIn(BaseModel):
    """Creation d'un reseau dans un projet (F7)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "lan-projet"}]})

    name: str = Field(min_length=1, max_length=128)


class NetworkUpdateIn(BaseModel):
    """Modification d'un reseau (renommage)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "nouveau-nom-lan"}]})

    name: str = Field(min_length=1, max_length=128)


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
    created_at: datetime
