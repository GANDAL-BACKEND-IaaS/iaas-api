from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import Base


class UserRef(Base):
    """Référence d'un utilisateur : l'identifiant fourni par l'IAM, rien d'autre."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)


class AdminRef(Base):
    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)