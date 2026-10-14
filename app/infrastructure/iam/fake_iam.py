import hashlib
import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field, replace
from datetime import timedelta

from app.application.ports.iam import (
    AlreadyMember,
    AuthToken,
    EmailAlreadyUsed,
    GlobalRole,
    IamPort,
    Identity,
    InvalidCredentials,
    MemberGrant,
    NotAMember,
    OwnerRightsImmutable,
    ProjectAlreadyExists,
    ProjectNotFound,
    Right,
    UnknownRight,
    UserNotFound,
    UserUpdate,
)
from app.core.tokens import decode_token, encode_token


def _hash(password: str) -> str:
    # Mock uniquement : un vrai IAM utilise bcrypt/argon2.
    return hashlib.sha256(password.encode()).hexdigest()


@dataclass
class _UserRecord:
    identity: Identity
    password_hash: str


@dataclass
class _ProjectRecord:
    owner_id: str
    grants: dict[str, frozenset[Right]] = field(default_factory=dict)  # membres non propriétaires


class FakeIamClient(IamPort):
    def __init__(
        self,
        known_rights: Iterable[Right],
        secret: str = "dev-secret",
        token_ttl: timedelta = timedelta(hours=1),
    ):
        self._known_rights = frozenset(known_rights)
        self._secret = secret
        self._ttl = token_ttl
        self._users: dict[str, _UserRecord] = {}
        self._projects: dict[str, _ProjectRecord] = {}

    # ---- hors port : préparer des données (l'inscription est gérée par l'IAM réel) ----
    def add_user(self, email: str, password: str, first_name: str = "", last_name: str = "",
                 role: GlobalRole = GlobalRole.USER, user_id: str | None = None) -> Identity:
        self._ensure_email_free(email)
        identity = Identity(user_id or str(uuid.uuid4()), email, first_name, last_name, role)
        self._users[identity.user_id] = _UserRecord(identity, _hash(password))
        return identity

    # ---- port ----
    async def login(self, email: str, password: str) -> AuthToken:
        record = next((r for r in self._users.values() if r.identity.email == email), None)
        if record is None or record.password_hash != _hash(password):
            raise InvalidCredentials()
        return self._issue_token(record.identity)

    async def validate_token(self, token: str) -> Identity:
        return decode_token(token, self._secret)

    async def update_user(self, user_id: str, changes: UserUpdate) -> AuthToken:
        record = self._get_user(user_id)
        if changes.email and changes.email != record.identity.email:
            self._ensure_email_free(changes.email)
        record.identity = replace(
            record.identity,
            email=changes.email if changes.email is not None else record.identity.email,
            first_name=changes.first_name if changes.first_name is not None else record.identity.first_name,
            last_name=changes.last_name if changes.last_name is not None else record.identity.last_name,
        )
        return self._issue_token(record.identity)

    async def change_password(self, user_id: str, old_password: str, new_password: str) -> None:
        record = self._get_user(user_id)
        if record.password_hash != _hash(old_password):
            raise InvalidCredentials()
        record.password_hash = _hash(new_password)

    async def delete_account(self, user_id: str) -> None:
        self._get_user(user_id)
        del self._users[user_id]
        for project in self._projects.values():
            project.grants.pop(user_id, None)

    async def create_project(self, user_id: str, project_id: str) -> None:
        self._get_user(user_id)
        if project_id in self._projects:
            raise ProjectAlreadyExists(project_id)
        self._projects[project_id] = _ProjectRecord(owner_id=user_id)

    async def invite_user(self, user_id: str, project_id: str, rights: Collection[Right]) -> None:
        self._get_user(user_id)
        project = self._get_project(project_id)
        if self._is_member(project, user_id):
            raise AlreadyMember(user_id)
        project.grants[user_id] = self._checked(rights)

    async def update_rights(self, user_id: str, project_id: str, rights: Collection[Right]) -> None:
        self._get_user(user_id)
        project = self._get_project(project_id)
        if project.owner_id == user_id:
            raise OwnerRightsImmutable(user_id)
        if user_id not in project.grants:
            raise NotAMember(user_id)
        project.grants[user_id] = self._checked(rights)

    async def get_rights(self, user_id: str, project_id: str) -> frozenset[Right]:
        self._get_user(user_id)
        project = self._get_project(project_id)
        if project.owner_id == user_id:
            return self._known_rights
        return project.grants.get(user_id, frozenset())

    async def list_projects(self, user_id: str) -> frozenset[str]:
        self._get_user(user_id)
        return frozenset(pid for pid, p in self._projects.items() if self._is_member(p, user_id))

    async def list_members(self, project_id: str) -> tuple[MemberGrant, ...]:
        """Membres du projet. Le proprietaire recoit l'ensemble des droits connus."""
        project = self._get_project(project_id)
        owner = MemberGrant(project.owner_id, True, self._known_rights)
        guests = tuple(
            MemberGrant(user_id, False, rights) for user_id, rights in project.grants.items()
        )
        return (owner, *guests)

    # ---- privé ----
    def _issue_token(self, identity: Identity) -> AuthToken:
        return encode_token(identity, self._secret, self._ttl)

    def _checked(self, rights: Collection[Right]) -> frozenset[Right]:
        unknown = set(rights) - self._known_rights
        if unknown:
            raise UnknownRight(", ".join(sorted(unknown)))
        return frozenset(rights)

    @staticmethod
    def _is_member(project: _ProjectRecord, user_id: str) -> bool:
        return project.owner_id == user_id or user_id in project.grants

    def _get_user(self, user_id: str) -> _UserRecord:
        try:
            return self._users[user_id]
        except KeyError:
            raise UserNotFound(user_id) from None

    def _get_project(self, project_id: str) -> _ProjectRecord:
        try:
            return self._projects[project_id]
        except KeyError:
            raise ProjectNotFound(project_id) from None

    def _ensure_email_free(self, email: str) -> None:
        if any(r.identity.email == email for r in self._users.values()):
            raise EmailAlreadyUsed(email)