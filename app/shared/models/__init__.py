"""Enregistrement des modeles SQLAlchemy sur le metadata partage.

Importer ce module suffit pour que Base.metadata connaisse toutes les tables.
"""

from . import audit, identities, networks, packs, projects, requests, rights, shares, storages, vms

__all__ = [
    "audit",
    "identities",
    "networks",
    "packs",
    "projects",
    "requests",
    "rights",
    "shares",
    "storages",
    "vms",
]
