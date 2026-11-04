"""Injection des ports et de la configuration.

Point unique de branchement : les mocks seront remplaces par les vrais clients ici,
sans toucher a la logique metier.
"""

from collections.abc import Callable
from datetime import timedelta
from functools import lru_cache

from app.application.ports.decision import DecisionPort
from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import GlobalRole, IamPort, Identity
from app.application.ports.network import NetworkPort
from app.application.ports.notifications import NotificationsPort
from app.core.settings import get_settings
from app.core.tokens import decode_token
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor
from app.infrastructure.iam.fake_iam import FakeIamClient, stable_user_id
from app.infrastructure.network.fake_network import FakeNetwork
from app.infrastructure.notifications.fake_notifications import FakeNotifications
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
def get_notifications() -> NotificationsPort:
    """Mock de notifications, remplace par le canal reel au moment de l'integration."""
    return FakeNotifications()


@lru_cache
def get_decision() -> DecisionPort | None:
    """Point unique de branchement du service de DECISION et de QUOTA.

    `@lru_cache` est délibéré : le client porte une session de rôle obtenue par
    `/sts/assume-role`, et en endosser une par requête multiplierait les appels
    sans rien gagner. La session est bornée et révocable — c'est son intérêt.
    """
    settings = get_settings()
    if settings.decision_backend == "off":
        # Rien n est demande a IAM. `authorize` le voit et garde son
        # comportement d avant — la greffe est inerte, pas permissive par
        # accident : elle n a simplement pas d interlocuteur.
        return None
    if settings.decision_backend == "fake":
        from app.infrastructure.iam.fake_decision import FakeDecisionClient
        return FakeDecisionClient(plan_par_defaut=settings.decision_fake_quota)
    # L'import est ICI et non en tête de fichier : le module réel exige
    # `gandal_garde`, et un backend en mode « fake » doit démarrer sans lui.
    from gandal_garde import ClientIam

    from app.infrastructure.iam.gandal_decision import GandalDecisionClient
    return GandalDecisionClient(ClientIam(
        settings.decision_url, settings.decision_key_file,
        role=settings.decision_role, fichier_ca=settings.decision_ca_file,
        delai_s=settings.decision_timeout_seconds))
