"""Port Hyperviseur (XCP-ng).

Le backend ne connait que ce contrat : entrees, sorties, erreurs.
Chaque appel a un delai maximal cote adaptateur et doit pouvoir etre rejoue sans effet de bord.
Les unites sont explicites : RAM, VRAM et SSD en Go, CPU en vCPU.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.shared.enums import PowerAction


class HypervisorError(Exception):
    """Erreur remontee par le groupe Hyperviseur."""


class HypervisorUnavailable(HypervisorError):
    """Le groupe Hyperviseur ne repond pas dans le delai imparti."""


@dataclass(frozen=True)
class VmSpec:
    """Caracteristiques de base demandees a l'hyperviseur."""

    name: str
    ram_gb: int
    vcpu: int
    vram_gb: int
    ssd_gb: int


@dataclass(frozen=True)
class VmRef:
    """Identifiant d'une VM cote hyperviseur, avec l'adresse IP si deja attribuee."""

    vm_id: str
    ip_address: str | None = None


@dataclass(frozen=True)
class ConsoleAccess:
    """Moyen d'acces a la console graphique. Le backend n'etablit pas la connexion (F5)."""

    url: str
    expires_in: int


class HypervisorPort(ABC):
    """Actions techniques sur les VMs, fournies par le groupe Hyperviseur."""

    @abstractmethod
    async def create_vm(self, spec: VmSpec) -> VmRef:
        """Cree une VM. Rejouable : le meme appel ne cree pas une seconde VM."""

    @abstractmethod
    async def update_vm(self, ref: VmRef, spec: VmSpec) -> None:
        """Met a jour les caracteristiques de base d'une VM existante."""

    @abstractmethod
    async def power(self, ref: VmRef, action: PowerAction) -> None:
        """Demarre, arrete ou redemarre une VM (F4)."""

    @abstractmethod
    async def console(self, ref: VmRef) -> ConsoleAccess:
        """Fournit un acces a la console graphique d'une VM (F5)."""

    @abstractmethod
    async def delete_vm(self, ref: VmRef) -> None:
        """Supprime une VM. Rejouable si la VM est deja absente."""
