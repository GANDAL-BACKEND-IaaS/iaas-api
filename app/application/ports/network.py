"""Port Reseau.

Contrat a convenir avec le groupe Reseau : creer/renommer/supprimer un reseau,
rattacher une VM, l'en retirer.
Les appels sont rejouables sans effet de bord et bornes par un delai maximal.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.application.ports.hypervisor import VmRef


class NetworkError(Exception):
    """Erreur remontee par le groupe Reseau."""


class NetworkUnavailable(NetworkError):
    """Le groupe Reseau ne repond pas dans le delai imparti."""


@dataclass(frozen=True)
class NetworkRef:
    """Identifiant d'un reseau cote groupe Reseau."""

    network_id: str


class NetworkPort(ABC):
    """Actions techniques de mise en reseau des VMs."""

    @abstractmethod
    async def create_network(self, project_id: str, name: str) -> NetworkRef:
        """Cree un reseau dans un projet."""

    @abstractmethod
    async def rename_network(self, network: NetworkRef, name: str) -> None:
        """Renomme un reseau existant."""

    @abstractmethod
    async def attach_vm(self, network: NetworkRef, vm: VmRef) -> None:
        """Rattache une VM a un reseau. Sans effet si elle y est deja."""

    @abstractmethod
    async def detach_vm(self, network: NetworkRef, vm: VmRef) -> None:
        """Retire une VM d'un reseau. Sans effet si elle n'y est pas."""

    @abstractmethod
    async def detach_vm_from_project(self, vm: VmRef, project_id: str) -> None:
        """Retire une VM de tous les reseaux d'un projet (retrait de partage ou suppression)."""

    @abstractmethod
    async def delete_network(self, network: NetworkRef) -> None:
        """Supprime un reseau. Sans effet s'il est deja absent."""
