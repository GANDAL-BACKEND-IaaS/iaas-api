"""Adaptateur mock du port Hyperviseur, en attendant l'integration XCP-ng."""

import uuid

from app.application.ports.hypervisor import (
    ConsoleAccess,
    HypervisorPort,
    HypervisorUnavailable,
    VmRef,
    VmSpec,
)
from app.shared.enums import PowerAction


class FakeHypervisor(HypervisorPort):
    """Memoire locale des VMs. `available=False` simule une indisponibilite."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.vms: dict[str, VmSpec] = {}
        self.ips: dict[str, str] = {}
        self.power_log: list[tuple[str, PowerAction]] = []
        self._next_ip = 10

    def _guard(self) -> None:
        if not self.available:
            raise HypervisorUnavailable("hyperviseur indisponible")

    def _allocate_ip(self) -> str:
        self._next_ip += 1
        return f"192.0.2.{self._next_ip}"

    async def create_vm(self, spec: VmSpec) -> VmRef:
        """Cree une VM mockee et retourne sa reference, avec une IP fictive."""
        self._guard()
        vm_id = str(uuid.uuid4())
        self.vms[vm_id] = spec
        self.ips[vm_id] = self._allocate_ip()
        return VmRef(vm_id, self.ips[vm_id])

    async def update_vm(self, ref: VmRef, spec: VmSpec) -> None:
        """Remplace les caracteristiques memoirees de la VM."""
        self._guard()
        if ref.vm_id not in self.vms:
            raise KeyError(ref.vm_id)
        self.vms[ref.vm_id] = spec

    async def power(self, ref: VmRef, action: PowerAction) -> None:
        """Enregistre l'action d'alimentation."""
        self._guard()
        if ref.vm_id not in self.vms:
            raise KeyError(ref.vm_id)
        self.power_log.append((ref.vm_id, action))

    async def console(self, ref: VmRef) -> ConsoleAccess:
        """Retourne une URL de console fictive."""
        self._guard()
        if ref.vm_id not in self.vms:
            raise KeyError(ref.vm_id)
        return ConsoleAccess(url=f"https://console.local/{ref.vm_id}", expires_in=300)

    async def delete_vm(self, ref: VmRef) -> None:
        """Supprime la VM. Sans effet si elle est deja absente (rejouable)."""
        self._guard()
        self.vms.pop(ref.vm_id, None)
        self.ips.pop(ref.vm_id, None)
