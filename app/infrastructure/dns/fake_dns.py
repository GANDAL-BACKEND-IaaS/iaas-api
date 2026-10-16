"""Adaptateur mock du port DNS, en attendant l'equipe tierce.

En plus du cas nominal, il sait reproduire les pannes de l'equipe DNS pour tester les
appelants : indisponibilite, reponse perdue et refus definitif.
"""

from app.application.ports.dns import DnsPort, DnsRejected, DnsUnavailable


class FakeDns(DnsPort):
    """Memorise les demandes de suppression de nom de domaine et simule les pannes."""

    def __init__(self, available: bool = True) -> None:
        """Cree un mock vide. available=False rend l'equipe DNS indisponible en permanence."""
        self.available = available
        self.deleted: list[str] = []          # VMs dont le nom est supprime, sans doublon
        self.received: dict[str, int] = {}    # nombre de demandes recues par VM, renvois compris
        self._fail_next = 0
        self._lose_next = 0
        self._reject_next = 0

    def fail_next(self, calls: int = 1) -> None:
        """Les prochaines demandes echouent avant d'arriver a l'equipe DNS."""
        self._fail_next += calls

    def lose_next_responses(self, calls: int = 1) -> None:
        """Les prochaines demandes sont traitees, mais la reponse se perd en route."""
        self._lose_next += calls

    def reject_next(self, calls: int = 1) -> None:
        """Les prochaines demandes sont refusees de facon definitive."""
        self._reject_next += calls

    async def delete_domain(self, vm_id: str) -> None:
        """Enregistre une demande de suppression. Rejouable sans doublon."""
        if not self.available or self._fail_next:
            self._fail_next = max(self._fail_next - 1, 0)
            raise DnsUnavailable("dns indisponible")
        if self._reject_next:
            self._reject_next -= 1
            raise DnsRejected("demande refusee par l'equipe dns")
        self.received[vm_id] = self.received.get(vm_id, 0) + 1
        if vm_id not in self.deleted:
            self.deleted.append(vm_id)
        if self._lose_next:
            self._lose_next -= 1
            raise DnsUnavailable("reponse perdue : la suppression a bien ete prise en compte")
