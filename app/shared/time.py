"""Horloge du domaine. Toutes les dates metier sont en UTC."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Retourne l'instant courant en UTC, avec fuseau."""
    return datetime.now(UTC)
