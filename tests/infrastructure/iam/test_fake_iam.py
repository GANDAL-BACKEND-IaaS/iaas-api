from datetime import timedelta

import pytest

from app.application.ports.iam import (
    AlreadyMember,
    EmailAlreadyUsed,
    GlobalRole,
    InvalidCredentials,
    InvalidToken,
    NotAMember,
    OwnerRightsImmutable,
    ProjectAlreadyExists,
    ProjectNotFound,
    TokenExpired,
    UnknownRight,
    UserNotFound,
    UserUpdate,
)
from app.infrastructure.iam.fake_iam import FakeIamClient
from app.shared.seed.loader import load_rights_catalog

CATALOG = load_rights_catalog()


@pytest.fixture
def iam() -> FakeIamClient:
    return FakeIamClient(known_rights=CATALOG.right_codes, secret="test")


@pytest.fixture
def alice(iam):
    return iam.add_user("alice@x.cm", "pw1", "Alice", "Ngono")


# ---- jeton ----
async def test_login_token_carries_identity_and_role(iam, alice):
    token = await iam.login("alice@x.cm", "pw1")
    identity = await iam.validate_token(token.access_token)
    assert identity == alice
    assert identity.role == GlobalRole.USER


async def test_admin_role_in_token(iam):
    iam.add_user("root@x.cm", "pw", role=GlobalRole.ADMIN)
    token = await iam.login("root@x.cm", "pw")
    assert (await iam.validate_token(token.access_token)).role == GlobalRole.ADMIN


async def test_login_errors(iam, alice):
    with pytest.raises(InvalidCredentials):
        await iam.login("alice@x.cm", "nope")
    with pytest.raises(InvalidCredentials):
        await iam.login("inconnu@x.cm", "pw1")


async def test_find_user_id_by_email_ignores_case_and_spaces(iam, alice):
    """Le lookup email est utilisable tel que saisi par le frontend."""
    assert await iam.find_user_id_by_email("  ALICE@X.CM  ") == alice.user_id
    assert await iam.find_user_id_by_email("inconnu@x.cm") is None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer xyz"])
async def test_validate_rejects_garbage(iam, garbage):
    with pytest.raises(InvalidToken):
        await iam.validate_token(garbage)


async def test_validate_rejects_foreign_or_tampered_token(iam, alice):
    other = FakeIamClient(known_rights=CATALOG.right_codes, secret="autre")
    other.add_user("alice@x.cm", "pw1")
    foreign = await other.login("alice@x.cm", "pw1")
    with pytest.raises(InvalidToken):
        await iam.validate_token(foreign.access_token)

    token = (await iam.login("alice@x.cm", "pw1")).access_token
    with pytest.raises(InvalidToken):
        await iam.validate_token(token[:-2] + "xx")


async def test_validate_rejects_expired_token(alice):
    short = FakeIamClient(known_rights=CATALOG.right_codes, secret="t", token_ttl=timedelta(seconds=-1))
    short.add_user("a@x.cm", "pw")
    token = await short.login("a@x.cm", "pw")
    with pytest.raises(TokenExpired):
        await short.validate_token(token.access_token)


# ---- compte ----
async def test_update_returns_new_token_with_new_info(iam, alice):
    token = await iam.update_user(alice.user_id, UserUpdate(first_name="Alicia"))
    identity = await iam.validate_token(token.access_token)
    assert identity.first_name == "Alicia" and identity.last_name == "Ngono"


async def test_update_email_conflict(iam, alice):
    iam.add_user("bob@x.cm", "pw2")
    with pytest.raises(EmailAlreadyUsed):
        await iam.update_user(alice.user_id, UserUpdate(email="bob@x.cm"))


async def test_change_password(iam, alice):
    with pytest.raises(InvalidCredentials):
        await iam.change_password(alice.user_id, "mauvais", "new")
    await iam.change_password(alice.user_id, "pw1", "new")
    await iam.login("alice@x.cm", "new")
    with pytest.raises(InvalidCredentials):
        await iam.login("alice@x.cm", "pw1")


async def test_delete_account(iam, alice):
    await iam.delete_account(alice.user_id)
    with pytest.raises(InvalidCredentials):
        await iam.login("alice@x.cm", "pw1")
    with pytest.raises(UserNotFound):
        await iam.delete_account(alice.user_id)


# ---- projets et droits ----
async def test_owner_has_every_right(iam, alice):
    await iam.create_project(alice.user_id, "p1")
    assert await iam.get_rights(alice.user_id, "p1") == CATALOG.right_codes


async def test_invite_and_get_rights(iam, alice):
    bob = iam.add_user("bob@x.cm", "pw2")
    carl = iam.add_user("carl@x.cm", "pw3")
    await iam.create_project(alice.user_id, "p1")
    await iam.invite_user(bob.user_id, "p1", ["vm.view", "vm.console"])
    assert await iam.get_rights(bob.user_id, "p1") == {"vm.view", "vm.console"}
    assert await iam.get_rights(carl.user_id, "p1") == frozenset()


async def test_update_rights_replaces(iam, alice):
    bob = iam.add_user("bob@x.cm", "pw2")
    await iam.create_project(alice.user_id, "p1")
    await iam.invite_user(bob.user_id, "p1", ["vm.view"])
    await iam.update_rights(bob.user_id, "p1", ["storage.view"])
    assert await iam.get_rights(bob.user_id, "p1") == {"storage.view"}


async def test_rights_rules(iam, alice):
    bob = iam.add_user("bob@x.cm", "pw2")
    carl = iam.add_user("carl@x.cm", "pw3")
    await iam.create_project(alice.user_id, "p1")
    await iam.invite_user(bob.user_id, "p1", ["vm.view"])
    with pytest.raises(AlreadyMember):
        await iam.invite_user(bob.user_id, "p1", ["vm.view"])
    with pytest.raises(AlreadyMember):
        await iam.invite_user(alice.user_id, "p1", ["vm.view"])
    with pytest.raises(UnknownRight):
        await iam.invite_user(carl.user_id, "p1", ["vm.fly"])
    with pytest.raises(NotAMember):
        await iam.update_rights(carl.user_id, "p1", ["vm.view"])
    with pytest.raises(OwnerRightsImmutable):
        await iam.update_rights(alice.user_id, "p1", ["vm.view"])


async def test_list_projects(iam, alice):
    bob = iam.add_user("bob@x.cm", "pw2")
    await iam.create_project(alice.user_id, "p1")
    await iam.create_project(alice.user_id, "p2")
    await iam.invite_user(bob.user_id, "p2", ["vm.view"])
    assert await iam.list_projects(alice.user_id) == {"p1", "p2"}
    assert await iam.list_projects(bob.user_id) == {"p2"}


async def test_project_errors(iam, alice):
    await iam.create_project(alice.user_id, "p1")
    with pytest.raises(ProjectAlreadyExists):
        await iam.create_project(alice.user_id, "p1")
    with pytest.raises(ProjectNotFound):
        await iam.get_rights(alice.user_id, "inconnu")