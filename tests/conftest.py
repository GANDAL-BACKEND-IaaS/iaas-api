# LE DEFAUT DU CODE EST « gandal » : UN DEPLOIEMENT QUI OUBLIE LA VARIABLE
# DOIT EXIGER IAM, PAS S EN PASSER. C est la polarite correcte — une
# autorisation qui tombe en panne OUVERTE est pire qu un service qui refuse de
# demarrer, et « off » par defaut etait exactement ca.
#
# Ce sont donc LES TESTS qui disent explicitement qu ils ne veulent pas d IAM.
# C est ici qu il faut l exception, pas en production : la suite doit tourner
# sans cle, sans autorite et sans reseau.
#
# AVANT TOUT IMPORT DE « app » : les reglages sont lus au premier import, et
# poser la variable apres n aurait aucun effet.
import os

os.environ.setdefault("DECISION_BACKEND", "off")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.ports.iam import GlobalRole
from app.core.database import get_db
from app.core.dependencies import (
    get_hypervisor,
    get_iam,
    get_network,
    get_notifications,
)
from app.core.settings import get_settings
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor
from app.infrastructure.iam.fake_iam import FakeIamClient
from app.infrastructure.network.fake_network import FakeNetwork
from app.infrastructure.notifications.fake_notifications import FakeNotifications
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
def notifications():
    """Notifications mock neuves pour chaque test."""
    return FakeNotifications()


@pytest.fixture
def client(db, iam, hypervisor, network, notifications):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_iam] = lambda: iam
    app.dependency_overrides[get_hypervisor] = lambda: hypervisor
    app.dependency_overrides[get_network] = lambda: network
    app.dependency_overrides[get_notifications] = lambda: notifications
    yield TestClient(app)  # sans "with" : le lifespan (BD réelle) n'est pas lancé
    app.dependency_overrides.clear()