"""Schemas des packs de VM."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.time import UtcDateTime


class PackCreateIn(BaseModel):
    """Definition d'un pack par l'administrateur (F17)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Standard",
                    "description": "Configuration generale",
                    "ram_gb": 8,
                    "vcpu": 4,
                    "vram_gb": 0,
                    "ssd_gb": 80,
                }
            ]
        }
    )

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    ram_gb: int = Field(ge=1)
    vcpu: int = Field(ge=1)
    vram_gb: int = Field(ge=0)
    ssd_gb: int = Field(ge=1)


class PackUpdateIn(BaseModel):
    """Modification partielle d'un pack. Au moins un champ est requis."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    ram_gb: int | None = Field(default=None, ge=1)
    vcpu: int | None = Field(default=None, ge=1)
    vram_gb: int | None = Field(default=None, ge=0)
    ssd_gb: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _at_least_one(self) -> "PackUpdateIn":
        if all(
            value is None
            for value in (self.name, self.description, self.ram_gb, self.vcpu, self.vram_gb, self.ssd_gb)
        ):
            raise ValueError("Au moins un champ doit etre fourni.")
        return self


class PackOut(BaseModel):
    """Pack du catalogue."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    ram_gb: int
    vcpu: int
    vram_gb: int
    ssd_gb: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
