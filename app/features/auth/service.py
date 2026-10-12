from sqlalchemy.orm import Session

from app.application.ports.iam import GlobalRole, Identity
from app.shared.models.identities import AdminRef, UserRef


def ensure_reference(db: Session, identity: Identity) -> None:
    """Crée la référence locale à la première connexion (idempotent)."""
    model = AdminRef if identity.role == GlobalRole.ADMIN else UserRef
    if db.get(model, identity.user_id) is None:
        db.add(model(id=identity.user_id))
        db.commit()


def remove_reference(db: Session, user_id: str) -> None:
    for model in (UserRef, AdminRef):
        obj = db.get(model, user_id)
        if obj is not None:
            db.delete(obj)
    db.commit()