"""Adaptateur mock du port DNS, en attendant l'equipe tierce."""

from app.application.ports.dns import DnsPort, DnsUnavailable


class FakeDns(DnsPort):
    """Memorise les demandes de suppression de nom de domaine."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.deleted: list[str] = []

    async def delete_domain(self, vm_id: str) -> None:
        """Enregistre une demande de suppression. Rejouable sans doublon."""
        if not self.available:
            raise DnsUnavailable("dns indisponible")
        if vm_id not in self.deleted:
            self.deleted.append(vm_id)
