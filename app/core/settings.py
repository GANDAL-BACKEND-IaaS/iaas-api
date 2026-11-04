"""Configuration lue depuis l'environnement et le fichier .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parametres de l'application. Les valeurs d'environnement ecrasent les defauts."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    iam_jwt_secret: str = "dev-secret-change-me"
    iam_token_ttl_seconds: int = 3600

    database_url: str = "sqlite:///./dev.db"   # en prod : postgresql+psycopg://user:pwd@host/db
    iam_seed_demo_users: bool = True   # comptes de démo dans le mock IAM (dev uniquement)


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration memorisee pour le processus."""
    return Settings()