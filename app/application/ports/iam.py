from abc import ABC, abstractmethod
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

Right = str  # code de droit, ex. "vm.view". Le catalogue vit en BD / fichier, pas dans le code.


class GlobalRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True)
class Identity:
    """Ce que le backend lit dans un jeton valide."""
    user_id: str
    email: str
    first_name: str
    last_name: str
    role: GlobalRole


@dataclass(frozen=True)
class UserUpdate:
    """Champs à None = inchangés. Le mot de passe a sa propre opération."""
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


@dataclass(frozen=True)
class AuthToken:
    access_token: str
    expires_in: int
    token_type: str = "bearer"


@dataclass(frozen=True)
class MemberGrant:
    """Membre d'un projet tel que le port IAM le connait."""

    user_id: str
    is_owner: bool
    rights: frozenset[Right]


class IamError(Exception): ...
class InvalidCredentials(IamError): ...
class InvalidToken(IamError): ...
class TokenExpired(InvalidToken): ...
class UserNotFound(IamError): ...
class EmailAlreadyUsed(IamError): ...
class ProjectNotFound(IamError): ...
class ProjectAlreadyExists(IamError): ...
class AlreadyMember(IamError): ...
class NotAMember(IamError): ...
class OwnerRightsImmutable(IamError): ...
class UnknownRight(IamError): ...


class IamPort(ABC):
    @abstractmethod
    async def login(self, email: str, password: str) -> AuthToken:
        """Jeton contenant l'identité complète et le rôle global."""

    @abstractmethod
    async def validate_token(self, token: str) -> Identity:
        """Lit le jeton. Lève InvalidToken / TokenExpired s'il n'est pas exploitable."""

    @abstractmethod
    async def update_user(self, user_id: str, changes: UserUpdate) -> AuthToken:
        """Met à jour les infos et renvoie un nouveau jeton."""

    @abstractmethod
    async def change_password(self, user_id: str, old_password: str, new_password: str) -> None: ...

    @abstractmethod
    async def delete_account(self, user_id: str) -> None: ...

    @abstractmethod
    async def create_project(self, user_id: str, project_id: str) -> None:
        """L'utilisateur devient propriétaire : tous les droits sur le projet."""

    @abstractmethod
    async def invite_user(self, user_id: str, project_id: str, rights: Collection[Right]) -> None:
        """Rend l'utilisateur membre du projet avec exactement ces droits."""

    @abstractmethod
    async def update_rights(self, user_id: str, project_id: str, rights: Collection[Right]) -> None:
        """Remplace les droits d'un membre (hors propriétaire)."""

    @abstractmethod
    async def remove_member(self, user_id: str, project_id: str) -> None:
        """Retire un membre invite du projet et ses droits."""

    @abstractmethod
    async def get_user(self, user_id: str) -> Identity:
        """Retourne l'identite connue de l'IAM, ou leve UserNotFound."""

    @abstractmethod
    async def get_rights(self, user_id: str, project_id: str) -> frozenset[Right]:
        """Droits de l'utilisateur sur le projet. Vide s'il n'est pas membre."""

    @abstractmethod
    async def list_projects(self, user_id: str) -> frozenset[str]:
        """Identifiants des projets auxquels l'utilisateur a accès."""

    @abstractmethod
    async def list_members(self, project_id: str) -> tuple[MemberGrant, ...]:
        """Membres du projet, proprietaire inclus, avec leurs droits."""

    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        """Oublie le projet et les droits de ses membres."""

    @abstractmethod
    async def find_user_id_by_email(self, email: str) -> str | None:
        """Retourne l'identifiant si le compte existe, sinon None."""