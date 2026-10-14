"""Adaptateur mock du port de notifications, en attendant le canal reel."""

from app.application.ports.notifications import (
    Notification,
    NotificationsPort,
    NotificationsUnavailable,
)


class FakeNotifications(NotificationsPort):
    """Conserve les notifications en memoire pour les tests et le developpement."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.sent: list[Notification] = []

    async def notify(self, notification: Notification) -> None:
        """Enregistre la notification. Leve NotificationsUnavailable si le canal est coupe."""
        if not self.available:
            raise NotificationsUnavailable("notifications indisponibles")
        self.sent.append(notification)
