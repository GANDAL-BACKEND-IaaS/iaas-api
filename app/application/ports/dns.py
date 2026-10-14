"""Port DNS.

Le backend ne porte aucune donnee de nom de domaine. Il demande seulement la suppression
du nom de domaine lorsqu'une VM est supprimee (R24).
"""

from abc import ABC, abstractmethod


class DnsError(Exception):
    """Erreur remontee par l'equipe DNS."""


class DnsUnavailable(DnsError):
    """L'equipe DNS ne repond pas dans le delai imparti."""


class DnsPort(ABC):
    """Demande de suppression de nom de domaine, et rien d'autre."""

    @abstractmethod
    async def delete_domain(self, vm_id: str) -> None:
        """Demande la suppression du nom de domaine d'une VM. Rejouable."""
