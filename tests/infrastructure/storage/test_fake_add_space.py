"""Cas nominal de add_space, utilitaire hors port du mock."""

from app.application.ports.storage import StorageRef
from app.infrastructure.storage.fake_storage import FakeStorage


def test_add_space_declares_an_existing_space():
    """L'espace declare est connu du mock sous l'identifiant fourni."""
    storage = FakeStorage()
    assert storage.add_space("st-9", "media", 100) == StorageRef("st-9")
    assert storage.spaces["st-9"].size == 100
