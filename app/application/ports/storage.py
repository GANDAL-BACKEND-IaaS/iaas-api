"""Port Stockage.

Contrat a convenir avec le groupe Stockage : creation, redimensionnement, suppression.
Les appels sont rejouables sans effet de bord et bornes par un delai maximal.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageError(Exception):
    """Erreur remontee par le groupe Stockage."""


class StorageUnavailable(StorageError):
    """Le groupe Stockage ne repond pas dans le delai imparti."""


@dataclass(frozen=True)
class StorageSpec:
    """Nom et taille (Go) demandes au groupe Stockage."""

    name: str
    size_gb: int


@dataclass(frozen=True)
class StorageRef:
    """Identifiant d'un espace cote groupe Stockage, avec l'adresse IP si disponible."""

    storage_id: str
    ip_address: str | None = None


class StoragePort(ABC):
    """Actions techniques sur les espaces de stockage."""

    @abstractmethod
    async def create_storage(self, spec: StorageSpec) -> StorageRef:
        """Cree un espace de stockage."""

    @abstractmethod
    async def resize(self, ref: StorageRef, size_gb: int) -> None:
        """Modifie la taille d'un espace existant."""

    @abstractmethod
    async def delete_storage(self, ref: StorageRef) -> None:
        """Supprime un espace, meme s'il contient des donnees. Rejouable."""
