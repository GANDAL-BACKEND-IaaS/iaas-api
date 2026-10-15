"""Monde de test du stockage : projets, invites, stockages, partage et ports mockes.

Chaque test repart d'une base SQLite neuve, d'un mock IAM neuf et de mocks Stockage et
notifications neufs (fixtures `db`, `iam` du conftest racine).

- owner (u@x.cm) possede p1 et p2 ; other (o@x.cm) possede p3.
- guest (g@x.cm) est invite dans p1 (storage.view, storage.request_update)
  et dans p2 (storage.view seulement).
- st-1 "backup" 50 Go dans p1, partage vers p2 ; st-2 "media" 100 Go dans p2 ;
  st-3 "other" 20 Go dans p3. Les trois existent aussi dans le mock Stockage.
"""

from dataclasses import dataclass

import pytest

from app.core.dependencies import get_notifications, get_storage
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.infrastructure.storage.fake_storage import FakeStorage
from app.main import app
from app.shared.enums import ResourceType, ShareStatus
from app.shared.models.shares import ResourceShare
from tests.support import add_storage, login_header, own_project


@dataclass
class World:
    """Identifiants et en-tetes du monde de test."""

    owner_id: str
    guest_id: str
    other_id: str
    owner: dict[str, str]
    guest: dict[str, str]
    other: dict[str, str]
    admin: dict[str, str]
    share_id: int


@pytest.fixture
def storage_port() -> FakeStorage:
    """Mock du groupe Stockage, neuf a chaque test."""
    return FakeStorage()


@pytest.fixture
def notifications() -> FakeNotifications:
    """Mock des notifications, neuf a chaque test."""
    return FakeNotifications()


@pytest.fixture
def api(client, storage_port, notifications):
    """Client HTTP branche sur les mocks Stockage et notifications du test."""
    app.dependency_overrides[get_storage] = lambda: storage_port
    app.dependency_overrides[get_notifications] = lambda: notifications
    return client


async def build_world(db, iam, storage_port: FakeStorage) -> World:
    """Insere le monde decrit en tete de module, cote IAM, base et mock Stockage."""
    owner_id = await own_project(db, iam, "p1")
    await own_project(db, iam, "p2")
    guest_id = iam.add_user("g@x.cm", "pw", "Gaelle", "Invitee").user_id
    await iam.invite_user(guest_id, "p1", ["storage.view", "storage.request_update"])
    await iam.invite_user(guest_id, "p2", ["storage.view"])
    iam.add_user("o@x.cm", "pw", "Olivier", "Autre")
    other_id = await own_project(db, iam, "p3", email="o@x.cm")

    for storage_id, project_id, name, size in (
        ("st-1", "p1", "backup", 50),
        ("st-2", "p2", "media", 100),
        ("st-3", "p3", "other", 20),
    ):
        add_storage(db, project_id, storage_id, name=name, size=size)
        storage_port.add_space(storage_id, name, size)

    share = ResourceShare(
        resource_type=ResourceType.STORAGE.value,
        resource_id="st-1",
        origin_project_id="p1",
        dest_project_id="p2",
        created_by=owner_id,
        status=ShareStatus.ACTIVE.value,
    )
    db.add(share)
    db.commit()
    return World(
        owner_id=owner_id,
        guest_id=guest_id,
        other_id=other_id,
        owner=await login_header(iam, "u@x.cm"),
        guest=await login_header(iam, "g@x.cm"),
        other=await login_header(iam, "o@x.cm"),
        admin=await login_header(iam, "root@x.cm"),
        share_id=share.id,
    )


@pytest.fixture
async def world(db, iam, storage_port) -> World:
    """Monde de test pret a l'emploi."""
    return await build_world(db, iam, storage_port)
