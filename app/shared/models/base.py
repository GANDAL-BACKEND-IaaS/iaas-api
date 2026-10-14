"""Base declarative commune a tous les modeles."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata partage, cible des migrations Alembic."""