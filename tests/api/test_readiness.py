"""Sondes de sante et de disponibilite de l'application."""

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.main import app


class _UnavailableDatabase:
    """Remplace la session pour simuler une base injoignable."""

    def execute(self, *_args, **_kwargs):
        raise SQLAlchemyError("base indisponible")


def test_ready_is_documented_in_openapi():
    """La sonde de disponibilite est visible dans Swagger avec ses reponses."""
    operation = app.openapi()["paths"]["/ready"]["get"]
    assert operation["operationId"] == "get_readiness"
    assert "200" in operation["responses"]
    assert "503" in operation["responses"]


def test_ready_reports_database_connectivity(client):
    """L'application est prete quand la base repond."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_unavailable(client):
    """Une base injoignable rend l'application indisponible, avec l'enveloppe standard."""
    app.dependency_overrides[get_db] = lambda: _UnavailableDatabase()
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "upstream_unavailable"
    assert "details" in body["error"]


def test_health_stays_up_without_database(client):
    """La sonde de sante reste un test de vie, independant de la base."""
    app.dependency_overrides[get_db] = lambda: _UnavailableDatabase()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
