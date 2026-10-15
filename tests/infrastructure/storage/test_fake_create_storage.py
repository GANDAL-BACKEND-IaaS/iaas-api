"""Cas nominal et limite de create_storage sur le mock."""

import pytest

from app.application.ports.storage import StorageSpec, StorageUnavailable
from app.infrastructure.storage.fake_storage import FakeStorage


async def test_create_storage_returns_a_new_id():
    """Chaque creation renvoie un identifiant distinct et memorise l'espace."""
    storage = FakeStorage()
    first = await storage.create_storage(StorageSpec("docs", 10))
    second = await storage.create_storage(StorageSpec("docs", 10))
    assert first != second
    assert storage.spaces[first.storage_id] == StorageSpec("docs", 10)


async def test_create_storage_when_unavailable():
    """Groupe indisponible : StorageUnavailable et rien n'est cree."""
    storage = FakeStorage(available=False)
    with pytest.raises(StorageUnavailable):
        await storage.create_storage(StorageSpec("docs", 10))
    assert storage.spaces == {}
