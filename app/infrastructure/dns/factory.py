"""Choix de l'adaptateur DNS selon l'environnement.

Le mock reste le defaut. Pour brancher l'equipe DNS reelle, il suffira que
app/core/dependencies.get_dns() retourne build_dns() et de definir DNS_MODE=http.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.application.ports.dns import DnsPort
from app.infrastructure.dns.fake_dns import FakeDns
from app.infrastructure.dns.http_dns import HttpDns


class DnsSettings(BaseSettings):
    """Parametres du port DNS, lus dans les variables DNS_* ou le fichier .env."""
    model_config = SettingsConfigDict(env_prefix="DNS_", env_file=".env", extra="ignore")

    mode: Literal["fake", "http"] = "fake"
    base_url: str = "http://localhost:9000"
    token: str = ""
    timeout_seconds: float = 5.0
    attempts: int = 2


def build_dns(settings: DnsSettings | None = None) -> DnsPort:
    """Retourne le mock en mode fake, le client HTTP en mode http."""
    settings = settings or DnsSettings()
    if settings.mode == "http":
        return HttpDns(settings.base_url, settings.token, settings.timeout_seconds,
                       settings.attempts)
    return FakeDns()
