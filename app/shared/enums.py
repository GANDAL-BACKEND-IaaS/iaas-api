"""Enumerations du domaine Backend IaaS.

Ces valeurs sont le contrat partage entre les modeles, les schemas d'API et les services.
Elles reprennent les cycles de vie du document de conception (sections 6.1 a 6.3).
"""

from enum import StrEnum


class RequestStatus(StrEnum):
    """Cycle de vie d'une demande (figure 7). Les etats finaux ne sont plus modifiables."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    CANCELLED = "cancelled"


class RequestKind(StrEnum):
    """Nature d'une demande. Seules creation et modification passent par une demande (R2)."""

    VM_CREATE = "vm_create"
    VM_UPDATE = "vm_update"
    STORAGE_CREATE = "storage_create"
    STORAGE_UPDATE = "storage_update"


class ShareStatus(StrEnum):
    """Cycle de vie d'un partage (figure 9). Un partage revoque n'est jamais reactive."""

    ACTIVE = "active"
    REVOKED = "revoked"


class InvitationStatus(StrEnum):
    """Cycle de vie d'une invitation (figure 8)."""

    SENT = "sent"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    CANCELLED = "cancelled"


class MembershipRole(StrEnum):
    """Role d'un membre dans un projet (section 3.2)."""

    OWNER = "owner"
    GUEST = "guest"


class ResourceType(StrEnum):
    """Type de ressource IaaS. Une ressource est une VM ou un espace de stockage."""

    VM = "vm"
    STORAGE = "storage"


class VmState(StrEnum):
    """Etat local connu d'une VM. La consultation reste possible si l'hyperviseur est indisponible."""

    PENDING = "pending"
    CREATING = "creating"
    STOPPED = "stopped"
    RUNNING = "running"
    DELETING = "deleting"
    ERROR = "error"
    UNKNOWN = "unknown"


class PowerState(StrEnum):
    """Etat transitoire renvoye par une action d'alimentation (202 Accepted)."""

    STARTING = "starting"
    STOPPING = "stopping"
    RESTARTING = "restarting"


class StorageState(StrEnum):
    """Etat local connu d'un espace de stockage."""

    AVAILABLE = "available"
    DELETING = "deleting"


class PowerAction(StrEnum):
    """Action directe d'alimentation d'une VM (F4). Elle ne passe pas par une demande."""

    START = "start"
    STOP = "stop"
    RESTART = "restart"


# Etat local vise apres une action d'alimentation reussie, et etat transitoire expose.
POWER_TARGET: dict[PowerAction, tuple[VmState, PowerState]] = {
    PowerAction.START: (VmState.RUNNING, PowerState.STARTING),
    PowerAction.STOP: (VmState.STOPPED, PowerState.STOPPING),
    PowerAction.RESTART: (VmState.RUNNING, PowerState.RESTARTING),
}

# Etats depuis lesquels une action est autorisee.
POWER_ALLOWED: dict[PowerAction, frozenset[VmState]] = {
    PowerAction.START: frozenset({VmState.STOPPED}),
    PowerAction.STOP: frozenset({VmState.RUNNING}),
    PowerAction.RESTART: frozenset({VmState.RUNNING}),
}
