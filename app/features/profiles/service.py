from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.shared.models.rights import ProfileModel, RightModel


class ProfileError(Exception): ...
class ProfileNotFound(ProfileError): ...
class ProfileNameTaken(ProfileError): ...
class UnknownRights(ProfileError): ...


def _rights(db: Session, codes: Collection[str]) -> list[RightModel]:
    codes = set(codes)
    found = list(db.scalars(select(RightModel).where(RightModel.code.in_(codes))))
    missing = codes - {r.code for r in found}
    if missing:
        raise UnknownRights(", ".join(sorted(missing)))
    return found


def list_rights(db: Session) -> list[RightModel]:
    return list(db.scalars(select(RightModel).order_by(RightModel.code)))


def list_profiles(db: Session) -> list[ProfileModel]:
    return list(db.scalars(select(ProfileModel).order_by(ProfileModel.name)))


def get_profile(db: Session, profile_id: int) -> ProfileModel:
    profile = db.get(ProfileModel, profile_id)
    if profile is None:
        raise ProfileNotFound(str(profile_id))
    return profile


def create_profile(db: Session, name: str, description: str, right_codes: Collection[str]) -> ProfileModel:
    profile = ProfileModel(name=name, description=description, rights=_rights(db, right_codes))
    db.add(profile)
    return _commit(db, profile, name)


def update_profile(db: Session, profile_id: int, name: str | None = None,
                   description: str | None = None,
                   right_codes: Collection[str] | None = None) -> ProfileModel:
    profile = get_profile(db, profile_id)
    if name is not None:
        profile.name = name
    if description is not None:
        profile.description = description
    if right_codes is not None:
        profile.rights = _rights(db, right_codes)
    return _commit(db, profile, profile.name)


def delete_profile(db: Session, profile_id: int) -> None:
    db.delete(get_profile(db, profile_id))
    db.commit()


def resolve_rights(db: Session, profile_id: int | None, extra: Collection[str] = ()) -> frozenset[str]:
    """Droits effectifs d'une invitation : droits du profil + droits à la carte.
    Utilisé par la future fonctionnalité F13 avant d'appeler iam.invite_user."""
    codes = set(extra)
    if profile_id is not None:
        codes |= {r.code for r in get_profile(db, profile_id).rights}
    _rights(db, codes)  # vérifie que tous les droits existent
    return frozenset(codes)


def _commit(db: Session, profile: ProfileModel, name: str) -> ProfileModel:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ProfileNameTaken(name) from None
    return profile