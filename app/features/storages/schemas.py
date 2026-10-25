"""Schemas des espaces de stockage."""

from pydantic import BaseModel, ConfigDict

from app.shared.enums import StorageState
from app.shared.time import UtcDateTime


class StorageOut(BaseModel):
    """Espace de stockage renvoye par l'API, avec son IP et sa taille en Go."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_project_id: str
    name: str
    ip_address: str | None
    size_gb: int
    state: StorageState
    shared: bool = False
    created_at: UtcDateTime
