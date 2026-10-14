"""Port de notifications.

Informe l'utilisateur d'une decision sur sa demande, d'une mise a jour suite a un pack,
ou d'une invitation recue (exigence non fonctionnelle : notifications).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class NotificationsError(Exception):
    """Erreur remontee par le canal de notification."""


class NotificationsUnavailable(NotificationsError):
    """Le canal de notification ne repond pas dans le delai imparti."""


@dataclass(frozen=True)
class Notification:
    """Message destine a un utilisateur, sans donnee sensible."""

    user_id: str
    subject: str
    message: str


class NotificationsPort(ABC):
    """Envoi de notifications. L'implementation reelle viendra plus tard."""

    @abstractmethod
    async def notify(self, notification: Notification) -> None:
        """Delivre une notification. Rejouable : un doublon reste acceptable."""
