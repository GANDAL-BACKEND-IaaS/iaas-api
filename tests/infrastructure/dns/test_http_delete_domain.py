"""Cas nominal et limite de HttpDns.delete_domain, sans reseau grace a un transport simule."""

import httpx
import pytest

from app.application.ports.dns import DnsRejected, DnsUnavailable
from app.infrastructure.dns.http_dns import HttpDns


async def _no_wait(_seconds: float) -> None:
    """Remplace asyncio.sleep pour que les tests de relance soient instantanes."""


def _dns(handler, token: str = "", attempts: int = 2) -> HttpDns:
    """Client branche sur un faux serveur qui repond avec handler."""
    return HttpDns("http://dns.test/", token=token, attempts=attempts,
                   transport=httpx.MockTransport(handler), sleep=_no_wait)


async def test_request_follows_the_proposed_contract():
    """Methode, chemin, cle d'idempotence et jeton sont ceux du contrat."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    await _dns(handler, token="secret").delete_domain("vm/1")
    request = seen[0]
    assert request.method == "DELETE"
    assert request.url.raw_path == b"/v1/vms/vm%2F1/domain"
    assert request.headers["idempotency-key"] == "delete-domain-vm/1"
    assert request.headers["authorization"] == "Bearer secret"


async def test_no_token_means_no_authorization_header():
    """Sans jeton configure, aucun en-tete Authorization n'est envoye."""
    seen = []
    await _dns(lambda r: seen.append(r) or httpx.Response(200)).delete_domain("vm-1")
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize("code", [200, 202, 204, 404, 410])
async def test_success_or_already_gone(code):
    """Un nom supprime ou deja absent est un succes : la demande est rejouable."""
    await _dns(lambda r: httpx.Response(code)).delete_domain("vm-1")


@pytest.mark.parametrize("code", [400, 401, 403, 409, 422])
async def test_definitive_refusal_is_not_retried(code):
    """Un refus definitif leve DnsRejected des la premiere reponse."""
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(code, text="refus")

    with pytest.raises(DnsRejected):
        await _dns(handler).delete_domain("vm-1")
    assert len(calls) == 1


@pytest.mark.parametrize("code", [500, 502, 503, 408, 429])
async def test_transient_error_is_retried_then_unavailable(code):
    """Une erreur passagere est retentee une fois, puis remonte DnsUnavailable."""
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(code)

    with pytest.raises(DnsUnavailable):
        await _dns(handler).delete_domain("vm-1")
    assert len(calls) == 2


async def test_transient_error_then_success():
    """Si la nouvelle tentative reussit, aucune erreur ne remonte."""
    responses = iter([httpx.Response(503), httpx.Response(204)])
    await _dns(lambda r: next(responses)).delete_domain("vm-1")


async def test_timeout_and_connection_error():
    """Un delai depasse ou un service injoignable donnent DnsUnavailable."""
    def timeout(request):
        raise httpx.ReadTimeout("lent", request=request)

    def refused(request):
        raise httpx.ConnectError("refuse", request=request)

    with pytest.raises(DnsUnavailable):
        await _dns(timeout, attempts=1).delete_domain("vm-1")
    with pytest.raises(DnsUnavailable):
        await _dns(refused, attempts=1).delete_domain("vm-1")
