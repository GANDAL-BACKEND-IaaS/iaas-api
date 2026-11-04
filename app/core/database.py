"""Session SQLAlchemy. SQLite en test, PostgreSQL dans le conteneur."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings

_url = get_settings().database_url
engine = create_engine(_url, connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Fournit une session et la ferme a la fin de la requete."""
    with SessionLocal() as session:
        yield session