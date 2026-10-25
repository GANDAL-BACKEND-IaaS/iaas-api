"""Schemas d'entree et de sortie du moteur de demandes."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.enums import RequestKind, RequestStatus
from app.shared.time import UtcDateTime


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Le nom ne peut pas etre vide.")
    return value.strip()


class VmConfigurationIn(BaseModel):
    """Configuration complete d'une VM, en unites explicites."""

    ram_gb: int = Field(ge=1)
    vcpu: int = Field(ge=1)
    vram_gb: int = Field(ge=0)
    ssd_gb: int = Field(ge=1)


class VMCreateRequestIn(BaseModel):
    """Demande de creation de VM : exactement un pack ou une configuration (F1, R13)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"name": "web-01", "pack_id": "pack-standard"},
                {
                    "name": "web-01",
                    "configuration": {"ram_gb": 8, "vcpu": 4, "vram_gb": 0, "ssd_gb": 80},
                },
            ]
        }
    )

    name: str = Field(min_length=1, max_length=128)
    pack_id: str | None = None
    configuration: VmConfigurationIn | None = None

    _trim = field_validator("name")(_not_blank)

    @model_validator(mode="after")
    def _exactly_one_mode(self) -> "VMCreateRequestIn":
        if (self.pack_id is None) == (self.configuration is None):
            raise ValueError("Fournir exactement un des champs pack_id ou configuration.")
        return self


class VMUpdateRequestIn(BaseModel):
    """Configuration complete souhaitee d'une VM existante (F2)."""

    configuration: VmConfigurationIn


class StorageCreateRequestIn(BaseModel):
    """Demande de creation : nom et taille en Go (F8)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "backup-alpha", "size_gb": 50}]})

    name: str = Field(min_length=1, max_length=128)
    size_gb: int = Field(ge=1)

    _trim = field_validator("name")(_not_blank)


class StorageUpdateRequestIn(BaseModel):
    """Demande de modification de la taille, en Go (F9)."""

    size_gb: int = Field(ge=1)


class RequestDecisionIn(BaseModel):
    """Decision d'un administrateur. La remarque est optionnelle (R4)."""

    note: str | None = Field(default=None, max_length=1000)


class RequestOut(BaseModel):
    """Demande telle que renvoyee par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    author_id: str
    kind: RequestKind
    status: RequestStatus
    payload: dict
    target_resource_type: str | None
    target_resource_id: str | None
    admin_note: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    decided_at: UtcDateTime | None
