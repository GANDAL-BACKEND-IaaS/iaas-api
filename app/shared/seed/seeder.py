import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.models.packs import Pack
from app.shared.models.rights import ProfileModel, RightModel
from app.shared.seed.loader import load_default_packs, load_default_profiles, load_rights_catalog


def stable_seed_id(kind: str, name: str) -> str:
    """UUID deterministe d'une donnee de reference : stable entre deux bases neuves."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"iaas:{kind}:{name}"))


def seed_rights(db: Session) -> None:
    """Synchronise le catalogue : ajoute les droits manquants, ne supprime rien."""
    existing = set(db.scalars(select(RightModel.code)))
    for right in load_rights_catalog().rights:
        if right.code not in existing:
            db.add(RightModel(code=right.code, description=right.description))
    db.commit()


def seed_default_packs(db: Session) -> None:
    """Packs initiaux, inseres uniquement si aucun pack n'existe."""
    if db.scalar(select(Pack.id).limit(1)) is not None:
        return
    for pack in load_default_packs():
        db.add(
            Pack(
                id=stable_seed_id("pack", pack.name),
                name=pack.name,
                description=pack.description,
                ram_gb=pack.ram_gb,
                vcpu=pack.vcpu,
                vram_gb=pack.vram_gb,
                ssd_gb=pack.ssd_gb,
            )
        )
    db.commit()


def seed_default_profiles(db: Session) -> None:
    """Profils initiaux, inseres uniquement si aucun profil n'existe."""
    if db.scalar(select(ProfileModel.id).limit(1)) is not None:
        return
    rights = {r.code: r for r in db.scalars(select(RightModel))}
    for profile in load_default_profiles():
        db.add(
            ProfileModel(
                id=stable_seed_id("profile", profile.name),
                name=profile.name,
                description=profile.description,
                rights=[rights[c] for c in profile.rights],
            )
        )
    db.commit()
