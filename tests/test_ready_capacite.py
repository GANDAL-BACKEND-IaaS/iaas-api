"""« /ready » dit la CAPACITE, pas le reglage.

POURQUOI CE FICHIER EXISTE. Le 6 novembre 2026, ce point d API a annonce
« decision: gandal » sur une machine ou « gandal_garde » n etait meme pas
installe. L adaptateur ne pouvait pas etre construit, et toute decision aurait
leve ModuleNotFoundError au premier appel — mais une supervision lisant cette
valeur aurait conclu que tout allait bien.
"""
from __future__ import annotations

import pytest

from app.core.dependencies import get_decision
from app.main import app


def test_off_est_rapporte_tel_quel(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["decision"] == "off"


def test_un_adaptateur_INCONSTRUCTIBLE_est_dit_INDISPONIBLE(client, monkeypatch):
    """LE TEST QUI COMPTE. C est le cas reel du 6 novembre."""
    import app.main as principal

    def casse():
        raise ModuleNotFoundError("No module named 'gandal_garde'")

    monkeypatch.setattr(principal, "get_decision", casse)
    monkeypatch.setattr(principal.get_settings(), "decision_backend", "gandal",
                        raising=False)
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    assert "INDISPONIBLE" in r.json()["decision"], r.json()


def test_un_adaptateur_qui_marche_est_rapporte(client, monkeypatch):
    import app.main as principal

    monkeypatch.setattr(principal, "get_decision", lambda: object())
    monkeypatch.setattr(principal.get_settings(), "decision_backend", "gandal",
                        raising=False)
    assert client.get("/ready").json()["decision"] == "gandal"


def test_ready_ne_leve_PAS_503_quand_la_decision_manque(client, monkeypatch):
    """La base repond et les routes servent : « ready » reste 200, mais le dit.

    Lever 503 ferait sortir le service de l equilibrage alors qu il fonctionne
    — en mode degrade, ce qui est une information, pas une panne.
    """
    import app.main as principal

    monkeypatch.setattr(principal, "get_decision",
                        lambda: (_ for _ in ()).throw(RuntimeError("cle illisible")))
    monkeypatch.setattr(principal.get_settings(), "decision_backend", "gandal",
                        raising=False)
    r = client.get("/ready")
    assert r.status_code == 200
    assert "INDISPONIBLE" in r.json()["decision"]
