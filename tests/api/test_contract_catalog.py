"""Le catalogue de `API_ENDPOINTS.md` reste aligne sur les operations OpenAPI."""

import re
from pathlib import Path

from app.main import app

_CATALOG_LINE = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`\s*\|")
_METHODS = {"get", "post", "patch", "put", "delete"}
_INFRASTRUCTURE = {"/api/v1/health", "/ready"}


def test_catalog_table_matches_openapi_business_operations():
    """Toute operation metier documentee existe, et reciproquement."""
    catalog = {
        (match.group(1), match.group(2))
        for line in (Path(__file__).resolve().parents[2] / "API_ENDPOINTS.md").read_text().splitlines()
        if (match := _CATALOG_LINE.match(line))
    }
    operations = {
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        if path not in _INFRASTRUCTURE
        for method in methods
        if method in _METHODS
    }

    assert catalog == operations
