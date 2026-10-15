"""Adaptateur mock du port Stockage, en attendant l'integration du groupe Stockage.

Aucun appel reseau : les espaces vivent en memoire, le temps du processus.
"""

import uuid

from app.application.ports.storage import (
    StorageNotFound,
    StoragePort,
    StorageRef,
    StorageSpec,
    StorageUnavailable,
)


class FakeStorage(StoragePort):
    """Memoire locale des espaces. `available=False` simule une indisponibilite du groupe."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.spaces: dict[str, StorageSpec] = {}

    def _guard(self) -> None:
        """Simule la panne du groupe Stockage quand `available` est faux."""
        if not self.available:
            raise StorageUnavailable("stockage indisponible")

    def add_space(self, storage_id: str, name: str, size: int) -> StorageRef:
        """Hors port : declare un espace deja existant (donnees de test ou de demo)."""
        self.spaces[storage_id] = StorageSpec(name=name, size=size)
        return StorageRef(storage_id)

    async def create_storage(self, spec: StorageSpec) -> StorageRef:
        """Cree un espace mocke et renvoie un identifiant neuf."""
        self._guard()
        storage_id = str(uuid.uuid4())
        self.spaces[storage_id] = spec
        return StorageRef(storage_id)

    async def resize(self, ref: StorageRef, size: int) -> None:
        """Change la taille memorisee de l'espace. StorageNotFound s'il est inconnu."""
        self._guard()
        current = self.spaces.get(ref.storage_id)
        if current is None:
            raise StorageNotFound(ref.storage_id)
        self.spaces[ref.storage_id] = StorageSpec(name=current.name, size=size)

    async def delete_storage(self, ref: StorageRef) -> None:
        """Supprime l'espace. Sans effet s'il est deja absent (rejouable)."""
        self._guard()
        self.spaces.pop(ref.storage_id, None)
