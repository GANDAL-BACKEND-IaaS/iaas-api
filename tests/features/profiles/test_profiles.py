import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.ports.iam import GlobalRole
from app.core.database import get_db
from app.core.dependencies import get_iam
from app.core.settings import get_settings
from app.features.profiles import service
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
    iam.add_user("u@x.cm", "pw")
    iam.add_user("root@x.cm", "pw", role=GlobalRole.ADMIN)
    return iam


@pytest.fixture
def client(db, iam):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_iam] = lambda: iam
    yield TestClient(app)  # sans "with" : le lifespan (BD réelle) n'est pas lancé
    app.dependency_overrides.clear()


async def _headers(iam, email):
    return {"Authorization": f"Bearer {(await iam.login(email, 'pw')).access_token}"}


def test_default_profiles_seeded_once(db):
    assert [p.name for p in service.list_profiles(db)] == ["Gestionnaire", "Lecteur", "Opérateur"]
    service.delete_profile(db, service.list_profiles(db)[0].id)
    seed_default_profiles(db)  # table non vide : rien n'est ré-inséré
    assert len(service.list_profiles(db)) == 2


async def test_admin_full_crud(client, iam):
    h = await _headers(iam, "root@x.cm")
    created = client.post("/admin/profiles", headers=h, json={
        "name": "Auditeur", "rights": ["vm.view", "storage.view"]}).json()
    assert created["rights"] == ["storage.view", "vm.view"]

    pid = created["id"]
    patched = client.patch(f"/admin/profiles/{pid}", headers=h,
                           json={"name": "Super auditeur", "rights": ["vm.view"]}).json()
    assert patched["name"] == "Super auditeur" and patched["rights"] == ["vm.view"]

    assert client.delete(f"/admin/profiles/{pid}", headers=h).status_code == 204
    assert client.patch(f"/admin/profiles/{pid}", headers=h, json={"name": "x"}).status_code == 404


async def test_default_profiles_are_editable(client, iam, db):
    h = await _headers(iam, "root@x.cm")
    lecteur = next(p for p in service.list_profiles(db) if p.name == "Lecteur")
    r = client.patch(f"/admin/profiles/{lecteur.id}", headers=h, json={"rights": ["vm.view", "vm.power"]})
    assert r.status_code == 200 and r.json()["rights"] == ["vm.power", "vm.view"]


async def test_validation_errors(client, iam):
    h = await _headers(iam, "root@x.cm")
    assert client.post("/admin/profiles", headers=h,
                       json={"name": "Lecteur"}).status_code == 409
    assert client.post("/admin/profiles", headers=h,
                       json={"name": "Z", "rights": ["vm.fly"]}).status_code == 422


async def test_non_admin_can_read_but_not_mutate(client, iam, db):
    assert client.get("/admin/profiles").status_code == 401
    assert client.get("/admin/rights").status_code == 401

    h = await _headers(iam, "u@x.cm")
    assert client.get("/admin/profiles", headers=h).status_code == 200
    assert client.get("/admin/rights", headers=h).status_code == 200

    assert client.post("/admin/profiles", headers=h,
                       json={"name": "Pirate", "rights": ["vm.delete"]}).status_code == 403
    lecteur = next(p for p in service.list_profiles(db) if p.name == "Lecteur")
    assert client.patch(f"/admin/profiles/{lecteur.id}", headers=h,
                        json={"name": "Piraté"}).status_code == 403
    assert client.delete(f"/admin/profiles/{lecteur.id}", headers=h).status_code == 403


def test_resolve_rights_profile_plus_extras(db):
    lecteur = next(p for p in service.list_profiles(db) if p.name == "Lecteur")
    assert service.resolve_rights(db, lecteur.id, ["vm.delete"]) == {"vm.view", "storage.view", "vm.delete"}
    with pytest.raises(service.UnknownRights):
        service.resolve_rights(db, None, ["vm.fly"])