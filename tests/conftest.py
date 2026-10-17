import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.ports.iam import GlobalRole
from app.core.database import get_db
from app.core.dependencies import (
    get_dns,
    get_hypervisor,
    get_iam,
    get_network,
    get_notifications,
    get_storage,
)
from app.core.settings import get_settings
from app.infrastructure.dns.fake_dns import FakeDns
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor
from app.infrastructure.iam.fake_iam import FakeIamClient
from app.infrastructure.network.fake_network import FakeNetwork
from app.infrastructure.notifications.fake_notifications import FakeNotifications
from app.infrastructure.storage.fake_storage import FakeStorage
from app.main import app
from app.shared import models as _models  # noqa: F401  enregistre toutes les tables
from app.shared.models.base import Base
from app.shared.seed.loader import load_rights_catalog
from app.shared.seed.seeder import seed_default_profiles, seed_rights


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        seed_rights(session)
        seed_default_profiles(session)
        yield session


@pytest.fixture
def iam():
    iam = FakeIamClient(known_rights=load_rights_catalog().right_codes,
                        secret=get_settings().iam_jwt_secret)
    iam.add_user("u@x.cm", "pw", "Ulrich", "Kamga")
    iam.add_user("root@x.cm", "pw", role=GlobalRole.ADMIN)
    return iam


@pytest.fixture
def hypervisor():
    """Hyperviseur mock neuf pour chaque test."""
    return FakeHypervisor()


@pytest.fixture
def network():
    """Reseau mock neuf pour chaque test."""
    return FakeNetwork()


@pytest.fixture
def dns():
    """DNS mock neuf pour chaque test."""
    return FakeDns()


@pytest.fixture
def notifications():
    """Notifications mock neuves pour chaque test."""
    return FakeNotifications()


@pytest.fixture
def storage_port():
    """Stockage mock neuf pour chaque test."""
    return FakeStorage()


@pytest.fixture
def client(db, iam, hypervisor, network, dns, notifications, storage_port):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_iam] = lambda: iam
    app.dependency_overrides[get_hypervisor] = lambda: hypervisor
    app.dependency_overrides[get_network] = lambda: network
    app.dependency_overrides[get_dns] = lambda: dns
    app.dependency_overrides[get_notifications] = lambda: notifications
    app.dependency_overrides[get_storage] = lambda: storage_port
    yield TestClient(app)  # sans "with" : le lifespan (BD réelle) n'est pas lancé
    app.dependency_overrides.clear()