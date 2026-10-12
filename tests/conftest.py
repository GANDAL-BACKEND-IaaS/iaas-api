import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.ports.iam import GlobalRole
from app.core.database import get_db
from app.core.dependencies import get_iam
from app.core.settings import get_settings
from app.infrastructure.iam.fake_iam import FakeIamClient
from app.main import app
from app.shared.models import identities, rights  # noqa: F401
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
def client(db, iam):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_iam] = lambda: iam
    yield TestClient(app)  # sans "with" : le lifespan (BD réelle) n'est pas lancé
    app.dependency_overrides.clear()