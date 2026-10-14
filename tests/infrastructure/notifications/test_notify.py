"""Cas nominal et limite de notify."""

import pytest

from app.application.ports.notifications import Notification, NotificationsUnavailable
from app.infrastructure.notifications.fake_notifications import FakeNotifications


async def test_notify_stores_the_message():
    """Le mock conserve le message sans donnee technique externe."""
    channel = FakeNotifications()
    await channel.notify(Notification("u1", "Decision", "Acceptee"))
    assert channel.sent[0].user_id == "u1"


async def test_notify_when_unavailable():
    """Un canal coupe n'enregistre pas le message."""
    channel = FakeNotifications(available=False)
    with pytest.raises(NotificationsUnavailable):
        await channel.notify(Notification("u1", "Decision", "Acceptee"))
    assert channel.sent == []
