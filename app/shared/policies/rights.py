"""Droits effectifs d'un membre : profil + droits additionnels.

Le proprietaire possede tous les droits connus. Un invite recoit l'union des droits
de son profil et de ses droits additionnels.
"""

from collections.abc import Collection, Iterable

from app.shared.enums import MembershipRole
from app.shared.models.projects import Membership
from app.shared.models.rights import ProfileModel


def effective_rights(
    *,
    role: str,
    profile: ProfileModel | None,
    additional_rights: Collection[str] | None,
    known_rights: Iterable[str],
) -> frozenset[str]:
    """Calcule l'ensemble des droits effectifs d'un membre."""
    if role == MembershipRole.OWNER.value:
        return frozenset(known_rights)
    codes = set(additional_rights or ())
    if profile is not None:
        codes |= {right.code for right in profile.rights}
    return frozenset(codes)


def membership_rights(membership: Membership, known_rights: Iterable[str]) -> frozenset[str]:
    """Raccourci pour une ligne d'appartenance chargee depuis la base."""
    return effective_rights(
        role=membership.role,
        profile=membership.profile,
        additional_rights=membership.additional_rights,
        known_rights=known_rights,
    )
