"""Adaptateur mock du port Reseau, en attendant l'integration du groupe Reseau."""

import uuid

from app.application.ports.hypervisor import VmRef
from app.application.ports.network import NetworkPort, NetworkRef, NetworkUnavailable


class FakeNetwork(NetworkPort):
    """Memoire locale des reseaux et des rattachements. `available=False` simule une panne."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.networks: dict[str, str] = {}
        self.links: set[tuple[str, str]] = set()
        self.project_of: dict[str, str] = {}

    def _guard(self) -> None:
        if not self.available:
            raise NetworkUnavailable("reseau indisponible")

    async def create_network(self, project_id: str, name: str) -> NetworkRef:
        """Cree un reseau mocke rattache a un projet."""
        self._guard()
        network_id = str(uuid.uuid4())
        self.networks[network_id] = name
        self.project_of[network_id] = project_id
        return NetworkRef(network_id)

    async def rename_network(self, network: NetworkRef, name: str) -> None:
        """Renomme un reseau existant."""
        self._guard()
        if network.network_id not in self.networks:
            raise KeyError(network.network_id)
        self.networks[network.network_id] = name

    async def attach_vm(self, network: NetworkRef, vm: VmRef) -> None:
        """Rattache une VM. Sans effet si le lien existe deja."""
        self._guard()
        self.links.add((network.network_id, vm.vm_id))

    async def detach_vm(self, network: NetworkRef, vm: VmRef) -> None:
        """Retire une VM. Sans effet si le lien est deja absent."""
        self._guard()
        self.links.discard((network.network_id, vm.vm_id))

    async def detach_vm_from_project(self, vm: VmRef, project_id: str) -> None:
        """Retire la VM de tous les reseaux du projet."""
        self._guard()
        targets = [net for net, owner in self.project_of.items() if owner == project_id]
        for network_id in targets:
            self.links.discard((network_id, vm.vm_id))

    async def delete_network(self, network: NetworkRef) -> None:
        """Supprime un reseau et ses liens. Sans effet s'il est deja absent."""
        self._guard()
        self.networks.pop(network.network_id, None)
        self.project_of.pop(network.network_id, None)
        self.links = {link for link in self.links if link[0] != network.network_id}
