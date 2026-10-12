import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.application.ports.iam import GlobalRole, Identity
from app.core.dependencies import get_iam
from app.core.settings import get_settings
from app.features.auth.dependencies import get_current_identity, require_admin
from app.infrastructure.iam.fake_iam import FakeIamClient


@pytest.fixture
def iam():
    iam = FakeIamClient(known_rights=set(), secret=get_settings().iam_jwt_secret)
    iam.add_user("u@x.cm", "pw")
    iam.add_user("root@x.cm", "pw", role=GlobalRole.ADMIN)
    return iam


@pytest.fixture
def client(iam):
    app = FastAPI()
    app.dependency_overrides[get_iam] = lambda: iam

    @app.get("/me")
    async def me(identity: Identity = Depends(get_current_identity)):
        return {"email": identity.email, "role": identity.role}

    @app.get("/admin")
    async def admin(_: Identity = Depends(require_admin)):
        return {"ok": True}

    return TestClient(app)


async def _auth(iam, email):
    token = await iam.login(email, "pw")
    return {"Authorization": f"Bearer {token.access_token}"}


async def test_valid_token_passes(client, iam):
    response = client.get("/me", headers=await _auth(iam, "u@x.cm"))
    assert response.status_code == 200 and response.json()["email"] == "u@x.cm"


def test_missing_or_bad_token_is_blocked(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


async def test_admin_only(client, iam):
    assert client.get("/admin", headers=await _auth(iam, "u@x.cm")).status_code == 403
    assert client.get("/admin", headers=await _auth(iam, "root@x.cm")).status_code == 200