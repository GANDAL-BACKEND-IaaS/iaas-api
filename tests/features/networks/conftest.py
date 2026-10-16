"""Fixtures specifiques a la suite de tests reseau."""

import pytest

from app.core.dependencies import get_network
from app.infrastructure.network.fake_network import FakeNetwork
from app.main import app


@pytest.fixture(autouse=True)
def fake_network():
    """Fournit un mock reseau isole et remis a zero pour chaque test."""
    mock = FakeNetwork()
    app.dependency_overrides[get_network] = lambda: mock
    yield mock
    mock.reset()
    app.dependency_overrides.pop(get_network, None)
