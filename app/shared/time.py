"""Horloge du domaine et serialisation des dates.

Toutes les dates metier sont en UTC. L'API expose le format ISO 8601 avec le
suffixe `Z` (ex. `2026-10-15T09:24:02Z`), y compris quand la base (SQLite en
test) renvoie une date naive.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def utcnow() -> datetime:
    """Retourne l'instant courant en UTC, avec fuseau."""
    return datetime.now(UTC)


def _iso_utc(value: datetime) -> str:
    """Serialise une date en ISO 8601 UTC avec suffixe `Z`."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str, when_used="json")]
"""Type Pydantic des dates sortantes : ISO 8601, fuseau UTC, suffixe `Z`."""
