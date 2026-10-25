"""Base declarative commune a tous les modeles."""

import uuid

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata partage, cible des migrations Alembic."""


def new_id() -> str:
    """Identifiant opaque UUID (chaine) utilise par tous les objets du domaine."""
    return str(uuid.uuid4())
