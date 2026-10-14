"""Adaptateur mock du port Stockage, en attendant l'integration du groupe Stockage."""

import uuid

from app.application.ports.storage import (
    StoragePort,
    StorageRef,
    StorageSpec,
    StorageUnavailable,
)


class FakeStorage(StoragePort):
    """Memoire locale des espaces. `available=False` simule une indisponibilite."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.spaces: dict[str, StorageSpec] = {}

    def _guard(self) -> None:
        if not self.available:
            raise StorageUnavailable("stockage indisponible")

    async def create_storage(self, spec: StorageSpec) -> StorageRef:
        """Cree un espace mocke."""
        self._guard()
        storage_id = str(uuid.uuid4())
        self.spaces[storage_id] = spec
        return StorageRef(storage_id)

    async def resize(self, ref: StorageRef, size: int) -> None:
        """Change la taille memoiree de l'espace."""
        self._guard()
        current = self.spaces[ref.storage_id]
        self.spaces[ref.storage_id] = StorageSpec(name=current.name, size=size)

    async def delete_storage(self, ref: StorageRef) -> None:
        """Supprime l'espace. Sans effet s'il est deja absent (rejouable)."""
        self._guard()
        self.spaces.pop(ref.storage_id, None)
