"""Client HTTP du port DNS, pour l'integration avec l'equipe DNS.

Contrat PROPOSE, a faire valider par l'equipe DNS :

    DELETE {base_url}/v1/vms/{vm_id}/domain
    Authorization: Bearer <jeton de service>      (si configure)
    Idempotency-Key: delete-domain-{vm_id}

Reponses :
- 2xx, 404 ou 410 : le nom est supprime, ou l'etait deja. La demande est rejouable.
- 408, 429, 5xx, delai depasse, service injoignable : DnsUnavailable, apres une nouvelle
  tentative rapide.
- autre 4xx : DnsRejected.

La cle d'idempotence ne depend que de la VM : un renvoi apres une reponse perdue est reconnu
comme la meme demande.
"""

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import quote

import httpx

from app.application.ports.dns import DnsPort, DnsRejected, DnsUnavailable

_ALREADY_GONE = {404, 410}
_RETRYABLE = {408, 429}


class HttpDns(DnsPort):
    """Appelle l'API de l'equipe DNS selon le contrat propose ci-dessus."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 5.0,
        attempts: int = 2,
        retry_delay: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Prepare le client. transport et sleep ne servent qu'aux tests."""
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._attempts = max(attempts, 1)
        self._retry_delay = retry_delay
        self._transport = transport
        self._sleep = sleep

    async def delete_domain(self, vm_id: str) -> None:
        """Demande la suppression du nom de domaine de la VM, avec une relance rapide."""
        last_error: DnsUnavailable | None = None
        for attempt in range(self._attempts):
            if attempt:
                await self._sleep(self._retry_delay)
            try:
                await self._send(vm_id)
                return
            except DnsUnavailable as exc:
                last_error = exc
        raise last_error

    async def _send(self, vm_id: str) -> None:
        """Une tentative d'appel. Traduit la reponse HTTP en succes ou en erreur du port."""
        headers = {"Idempotency-Key": f"delete-domain-{vm_id}"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        path = f"/v1/vms/{quote(vm_id, safe='')}/domain"
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout,
                                         transport=self._transport) as client:
                response = await client.delete(path, headers=headers)
        except httpx.TimeoutException as exc:
            raise DnsUnavailable(f"pas de reponse de l'equipe dns : {exc}") from None
        except httpx.HTTPError as exc:
            raise DnsUnavailable(f"equipe dns injoignable : {exc}") from None

        if response.is_success or response.status_code in _ALREADY_GONE:
            return
        detail = f"HTTP {response.status_code} : {response.text[:200]}"
        if response.status_code >= 500 or response.status_code in _RETRYABLE:
            raise DnsUnavailable(detail)
        raise DnsRejected(detail)
