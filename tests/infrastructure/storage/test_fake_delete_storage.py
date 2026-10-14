"""Cas nominal et limite de delete_storage sur le mock."""

from app.application.ports.storage import StorageRef, StorageSpec
from app.infrastructure.storage.fake_storage import FakeStorage


async def test_delete_storage_is_replayable():
    """Supprimer un espace deja absent ne leve pas d'erreur."""
    storage = FakeStorage()
    ref = await storage.create_storage(StorageSpec("docs", 10))
    await storage.resize(ref, 20)
    assert storage.spaces[ref.storage_id].size == 20
    await storage.delete_storage(ref)
    await storage.delete_storage(StorageRef("absent"))
    assert storage.spaces == {}
