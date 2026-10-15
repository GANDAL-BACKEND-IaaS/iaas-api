"""Cas nominal et limites de resize sur le mock."""

import pytest

from app.application.ports.storage import StorageNotFound, StorageRef, StorageUnavailable
from app.infrastructure.storage.fake_storage import FakeStorage


async def test_resize_is_replayable():
    """Fixer deux fois la meme taille donne le meme resultat."""
    storage = FakeStorage()
    ref = storage.add_space("st-1", "docs", 10)
    await storage.resize(ref, 30)
    await storage.resize(ref, 30)
    assert storage.spaces["st-1"].size == 30 and storage.spaces["st-1"].name == "docs"


async def test_resize_unknown_or_unavailable():
    """Espace inconnu : StorageNotFound. Groupe indisponible : StorageUnavailable."""
    storage = FakeStorage()
    with pytest.raises(StorageNotFound):
        await storage.resize(StorageRef("absent"), 5)
    storage.add_space("st-1", "docs", 10)
    storage.available = False
    with pytest.raises(StorageUnavailable):
        await storage.resize(StorageRef("st-1"), 20)
    assert storage.spaces["st-1"].size == 10
