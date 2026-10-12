from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.models.rights import ProfileModel, RightModel
from app.shared.seed.loader import load_default_profiles, load_rights_catalog


def seed_rights(db: Session) -> None:
    """Synchronise le catalogue : ajoute les droits manquants, ne supprime rien."""
    existing = set(db.scalars(select(RightModel.code)))
    for right in load_rights_catalog().rights:
        if right.code not in existing:
            db.add(RightModel(code=right.code, description=right.description))
    db.commit()


def seed_default_profiles(db: Session) -> None:
    """Profils initiaux, insérés uniquement si aucun profil n'existe."""
    if db.scalar(select(ProfileModel.id).limit(1)) is not None:
        return
    rights = {r.code: r for r in db.scalars(select(RightModel))}
    for p in load_default_profiles():
        db.add(ProfileModel(name=p.name, description=p.description,
                            rights=[rights[c] for c in p.rights]))
    db.commit()