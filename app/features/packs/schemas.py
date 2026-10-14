"""Schemas des packs de VM. Proprietaire : NAOMI."""

from pydantic import BaseModel, ConfigDict, Field


class PackIn(BaseModel):
    """Definition d'un pack par l'administrateur (F17)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "Standard", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}]}
    )

    name: str = Field(min_length=1, max_length=64)
    ram: int = Field(gt=0)
    cpu: int = Field(gt=0)
    vram: int = Field(gt=0)
    ssd: int = Field(gt=0)


class PackUpdateIn(BaseModel):
    """Modification partielle d'un pack. Les demandes en attente seront recalculees (R14)."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    ram: int | None = Field(default=None, gt=0)
    cpu: int | None = Field(default=None, gt=0)
    vram: int | None = Field(default=None, gt=0)
    ssd: int | None = Field(default=None, gt=0)


class PackOut(BaseModel):
    """Pack du catalogue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ram: int
    cpu: int
    vram: int
    ssd: int
