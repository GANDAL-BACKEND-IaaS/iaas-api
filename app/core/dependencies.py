"""Injection des ports et de la configuration.

Point unique de branchement : les mocks seront remplaces par les vrais clients ici,
sans toucher a la logique metier.
"""

from collections.abc import Callable
from datetime import timedelta
from functools import lru_cache

from app.application.ports.dns import DnsPort
from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import GlobalRole, IamPort, Identity
from app.application.ports.network import NetworkPort
from app.application.ports.notifications import NotificationsPort
from app.application.ports.storage import StoragePort
from app.core.settings import get_settings
from app.core.tokens import decode_token
from app.infrastructure.dns.fake_dns import FakeDns
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor
from app.infrastructure.iam.fake_iam import FakeIamClient, stable_user_id
from app.infrastructure.network.fake_network import FakeNetwork
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.infrastructure.storage.fake_storage import FakeStorage
from app.shared.seed.loader import load_rights_catalog


@lru_cache
def get_token_decoder() -> Callable[[str], Identity]:
    """Valide localement les jetons emis par l'IAM, sans le rappeler."""
    secret = get_settings().iam_jwt_secret
    return lambda token: decode_token(token, secret)


@lru_cache
def get_iam() -> IamPort:
    """Point unique de branchement IAM : mock aujourd'hui, client reel plus tard."""
    settings = get_settings()
    client = FakeIamClient(
        secret=settings.iam_jwt_secret,
        token_ttl=timedelta(seconds=settings.iam_token_ttl_seconds),
        known_rights=load_rights_catalog().right_codes,
    )
    if settings.iam_seed_demo_users:
        client.add_user(
            "admin@iaas.cm", "admin123", "Admin", "Root", GlobalRole.ADMIN,
            user_id=stable_user_id("admin@iaas.cm"),
        )
        client.add_user(
            "alice@iaas.cm", "alice123", "Alice", "Ngono",
            user_id=stable_user_id("alice@iaas.cm"),
        )
        client.add_user(
            "bob@iaas.cm", "bob123", "Bob", "Mbarga",
            user_id=stable_user_id("bob@iaas.cm"),
        )
    return client


@lru_cache
def get_hypervisor() -> HypervisorPort:
    """Mock hyperviseur, remplace par le client XCP-ng au moment de l'integration."""
    return FakeHypervisor()


@lru_cache
def get_network() -> NetworkPort:
    """Mock reseau, remplace par le client du groupe Reseau au moment de l'integration."""
    return FakeNetwork()


@lru_cache
def get_storage() -> StoragePort:
    """Mock stockage, remplace par le client du groupe Stockage au moment de l'integration."""
    return FakeStorage()


@lru_cache
def get_dns() -> DnsPort:
    """Mock DNS, remplace par le client de l'equipe tierce au moment de l'integration."""
    return FakeDns()


@lru_cache
def get_notifications() -> NotificationsPort:
    """Mock de notifications, remplace par le canal reel au moment de l'integration."""
    return FakeNotifications()
