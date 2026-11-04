"""Schemas VM."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.shared.enums import PowerAction, PowerState, VmState
from app.shared.time import UtcDateTime


class VMPowerIn(BaseModel):
    """Action directe d'alimentation (F4)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"action": "start"}]})

    action: PowerAction


class PowerOut(BaseModel):
    """Accuse d'une action d'alimentation : etat transitoire expose (202)."""

    vm_id: str
    action: PowerAction
    state: PowerState


class VMOut(BaseModel):
    """VM renvoyee par l'API, avec son IP et ses caracteristiques en unites explicites."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_project_id: str
    name: str
    ip_address: str | None
    ram_gb: int
    vcpu: int
    vram_gb: int
    ssd_gb: int
    state: VmState
    shared: bool = False
    created_at: UtcDateTime

    @field_validator("state", mode="before")
    @classmethod
    def _unknown_state(cls, value):
        """Un etat inconnu du backend est expose comme `unknown`, jamais comme un succes."""
        if isinstance(value, str) and value not in VmState._value2member_map_:
            return VmState.UNKNOWN
        return value


class ConsoleOut(BaseModel):
    """Acces a la console fourni par les groupes infrastructure (F5)."""

    url: str
    expires_in: int
