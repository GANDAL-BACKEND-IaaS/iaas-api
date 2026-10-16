import asyncio
import os
import uuid

from app.application.ports.hypervisor import VmRef
from app.application.ports.network import (
    NetworkNotFound,
    NetworkPort,
    NetworkRef,
    NetworkUnavailable,
)

_FLAG_DOWN_FILE = ".fake_network_down"


class FakeNetwork(NetworkPort):
    """Memoire locale des reseaux et des rattachements. `available=False` simule une panne."""

    def __init__(self, available: bool = True, delay_seconds: float = 0.0) -> None:
        self.available = available
        self.delay_seconds = delay_seconds
        self.networks: dict[str, str] = {}
        self.links: set[tuple[str, str]] = set()
        self.project_of: dict[str, str] = {}

    async def _guard(self) -> None:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if not self.available or os.path.exists(_FLAG_DOWN_FILE):
            raise NetworkUnavailable("reseau indisponible")

    def reset(self) -> None:
        """Remet a zero la memoire locale et restaure la disponibilite."""
        self.available = True
        self.delay_seconds = 0.0
        self.networks.clear()
        self.links.clear()
        self.project_of.clear()
        if os.path.exists(_FLAG_DOWN_FILE):
            try:
                os.remove(_FLAG_DOWN_FILE)
            except OSError:
                pass

    async def create_network(self, project_id: str, name: str) -> NetworkRef:
        """Cree un reseau mocke rattache a un projet."""
        await self._guard()
        network_id = str(uuid.uuid4())
        self.networks[network_id] = name
        self.project_of[network_id] = project_id
        return NetworkRef(network_id)

    async def attach_vm(self, network: NetworkRef, vm: VmRef) -> None:
        """Rattache une VM. Sans effet si le lien existe deja."""
        await self._guard()
        if network.network_id not in self.networks:
            raise NetworkNotFound(f"Reseau {network.network_id} introuvable.")
        self.links.add((network.network_id, vm.vm_id))

    async def detach_vm(self, network: NetworkRef, vm: VmRef) -> None:
        """Retire une VM. Sans effet si le lien est deja absent."""
        await self._guard()
        if network.network_id not in self.networks:
            raise NetworkNotFound(f"Reseau {network.network_id} introuvable.")
        self.links.discard((network.network_id, vm.vm_id))

    async def detach_vm_from_project(self, vm: VmRef, project_id: str) -> None:
        """Retire la VM de tous les reseaux du projet."""
        await self._guard()
        targets = [net for net, owner in self.project_of.items() if owner == project_id]
        for network_id in targets:
            self.links.discard((network_id, vm.vm_id))

    async def delete_network(self, network: NetworkRef) -> None:
        """Supprime un reseau et ses liens. Sans effet s'il est deja absent."""
        await self._guard()
        self.networks.pop(network.network_id, None)
        self.project_of.pop(network.network_id, None)
        self.links = {link for link in self.links if link[0] != network.network_id}
