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
        self.ips: dict[str, str] = {}
        self._next_ip = 80

    def _guard(self) -> None:
        if not self.available:
            raise StorageUnavailable("stockage indisponible")

    def _allocate_ip(self) -> str:
        self._next_ip += 1
        return f"192.0.2.{self._next_ip}"

    async def create_storage(self, spec: StorageSpec) -> StorageRef:
        """Cree un espace mocke, avec une IP fictive."""
        self._guard()
        storage_id = str(uuid.uuid4())
        self.spaces[storage_id] = spec
        self.ips[storage_id] = self._allocate_ip()
        return StorageRef(storage_id, self.ips[storage_id])

    async def resize(self, ref: StorageRef, size_gb: int) -> None:
        """Change la taille memoiree de l'espace."""
        self._guard()
        current = self.spaces[ref.storage_id]
        self.spaces[ref.storage_id] = StorageSpec(name=current.name, size_gb=size_gb)

    async def delete_storage(self, ref: StorageRef) -> None:
        """Supprime l'espace. Sans effet s'il est deja absent (rejouable)."""
        self._guard()
        self.spaces.pop(ref.storage_id, None)
        self.ips.pop(ref.storage_id, None)
