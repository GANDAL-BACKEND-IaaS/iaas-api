"""L adaptateur REEL contre un vrai serveur HTTP qui verifie la signature.

POURQUOI CE TEST EXISTE. Les tests unitaires utilisent `FakeDecisionClient` : ils
prouvent que la SEQUENCE est juste, pas que la chaine PARLE. Entre le backend et
le service de decision il y a `gandal_garde`, une signature GANDAL4-HMAC-SHA256,
un endossement de role, et un pont asynchrone vers une bibliotheque synchrone.
Chacun de ces quatre maillons peut casser sans qu aucun test unitaire ne bouge.

Le serveur monte ici VERIFIE la signature. Une signature fausse rend 401, et le
test echoue — ce qui est tout l interet : un bouchon qui accepte tout ne dirait
rien le jour ou le client et le service divergent.
"""
from __future__ import annotations

import http.server
import json
import os
import stat
import tempfile
import threading
from typing import ClassVar

import pytest

from app.application.ports.decision import Refuse, ServiceIndisponible

gandal_garde = pytest.importorskip(
    "gandal_garde",
    reason="pip install -e <Gandal>/iam/garde-serveur")

from app.infrastructure.iam.gandal_decision import GandalDecisionClient

ID_CLE, SECRET = "AKIAESSAI", "secret-d-essai-0123456789"


class FauxIam(http.server.BaseHTTPRequestHandler):
    """Repond comme le contrat, et EXIGE une signature bien formee."""

    journal: ClassVar[list[tuple[str, str, dict]]] = []
    refuser_decision = False

    def log_message(self, *_):
        pass

    def _rendre(self, statut, corps):
        donnees = json.dumps(corps).encode()
        self.send_response(statut)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        brut = self.rfile.read(n) if n else b""
        autorisation = self.headers.get("Authorization", "")
        # La signature doit etre presente, du bon algorithme, et porter les trois
        # en-tetes obligatoires du contrat.
        signes = (autorisation.split("SignedHeaders=")[1].split(",")[0].split(";")
                  if "SignedHeaders=" in autorisation else [])
        if (not autorisation.startswith("GANDAL4-HMAC-SHA256")
                or not {"host", "x-gandal-date", "x-gandal-nonce"} <= set(signes)
                or "Signature=" not in autorisation):
            return self._rendre(401, {"detail": "signature invalide ou incomplete"})
        corps = json.loads(brut) if brut else {}
        FauxIam.journal.append(("POST", self.path, corps))
        if self.path.endswith("/sts/assume-role"):
            return self._rendre(200, {"identifiants": {
                "id_cle": ID_CLE, "secret": SECRET, "jeton_session": "JETON"}})
        if self.path.endswith("/decisions"):
            if FauxIam.refuser_decision:
                return self._rendre(200, {"decision": "deny", "motif": "quota",
                                          "explication": "il vous reste 0 vCPU sur 4"})
            return self._rendre(200, {"decision": "permit",
                                      "explication": "2 vCPU restants"})
        if self.path.endswith("/quota-reservations"):
            return self._rendre(201, {"id": "res-1"})
        if "/commit" in self.path or "/release" in self.path:
            return self._rendre(200, {})
        return self._rendre(404, {"detail": self.path})

    def do_DELETE(self):
        FauxIam.journal.append(("DELETE", self.path, {}))
        return self._rendre(204, {})


@pytest.fixture
def iam_factice():
    FauxIam.journal = []
    FauxIam.refuser_decision = False
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FauxIam)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # Le fichier doit SURVIVRE a sa fermeture : la bibliotheque le relit par son
    # chemin et verifie son mode. D ou « mkstemp » plutot qu un gestionnaire de
    # contexte qui le supprimerait.
    descripteur, chemin = tempfile.mkstemp(suffix=".cle")
    with os.fdopen(descripteur, "w") as f:
        f.write(f"{ID_CLE} {SECRET}\n")
    os.chmod(chemin, 0o600)
    yield f"http://127.0.0.1:{srv.server_port}/v1", chemin
    srv.shutdown()
    os.unlink(chemin)


def adaptateur(url: str, cle: str) -> GandalDecisionClient:
    return GandalDecisionClient(gandal_garde.ClientIam(url, cle, role="backend"))


async def test_la_chaine_complete_parle(iam_factice):
    url, cle = iam_factice
    d = adaptateur(url, cle)
    explication = await d.autoriser(
        sujet="etu-1", action="vm:create",
        ressource={"type": "vm", "id": "poste-1", "projet": "p-vision"},
        contexte={"vcpu": 2, "ram_gb": 4, "disk_gb": 20})
    assert explication == "2 vCPU restants"
    chemins = [p.rsplit("/", 1)[-1] for m, p, _ in FauxIam.journal if m == "POST"]
    # L endossement de role precede la decision : sans lui, le service ne peut
    # pas decider AU NOM de quelqu un.
    assert chemins[:2] == ["assume-role", "decisions"]
    _, _, demande = next(x for x in FauxIam.journal if x[1].endswith("/decisions"))
    assert demande["sujet_delegue"] == "etu-1"


async def test_la_signature_est_acceptee_par_le_serveur(iam_factice):
    """Si elle etait fausse, le serveur rendrait 401 et l appel leverait."""
    url, cle = iam_factice
    await adaptateur(url, cle).autoriser(
        sujet="etu-1", action="vm:read", ressource={"type": "vm", "id": "x"})
    assert FauxIam.journal, "aucune requete n a atteint le serveur"


async def test_un_refus_d_iam_devient_un_Refuse_du_port(iam_factice):
    url, cle = iam_factice
    FauxIam.refuser_decision = True
    d = adaptateur(url, cle)
    with pytest.raises(Refuse) as exc:
        await d.autoriser(sujet="etu-1", action="vm:create",
                          ressource={"type": "vm", "id": "x", "projet": "p"},
                          contexte={"vcpu": 9, "ram_gb": 9, "disk_gb": 9})
    # Le motif d IAM traverse les deux couches : le backend ne doit pas rendre
    # « erreur interne » la ou IAM a ecrit une phrase utile.
    assert exc.value.motif == "quota"
    assert "0 vCPU sur 4" in exc.value.explication


async def test_la_transaction_libere_quand_la_creation_leve(iam_factice):
    url, cle = iam_factice
    d = adaptateur(url, cle)
    with pytest.raises(RuntimeError):
        async with d.transaction(sujet="etu-1", projet="p-vision",
                                 ressources={"vm_count": 1, "vcpu": 2}):
            raise RuntimeError("l hyperviseur a refuse")
    assert any(m == "DELETE" and "quota-reservations" in p
               for m, p, _ in FauxIam.journal), \
        "la reservation n a pas ete liberee : quota fantome"


async def test_confirmee_la_transaction_ne_libere_plus(iam_factice):
    url, cle = iam_factice
    d = adaptateur(url, cle)
    async with d.transaction(sujet="etu-1", projet="p-vision",
                             ressources={"vm_count": 1}) as t:
        await d.confirmer(t, id_ressource="poste-1", type_ressource="vm")
    assert any("commit" in p for m, p, _ in FauxIam.journal)
    assert not any(m == "DELETE" and "quota-reservations" in p
                   for m, p, _ in FauxIam.journal)


async def test_iam_injoignable_refuse_et_rend_503(iam_factice):
    """Le defaut est le refus : il n existe aucun chemin ou une panne autorise."""
    _, cle = iam_factice
    d = adaptateur("http://127.0.0.1:1/v1", cle)
    with pytest.raises(ServiceIndisponible) as exc:
        await d.autoriser(sujet="etu-1", action="vm:create",
                          ressource={"type": "vm", "id": "x"})
    assert exc.value.statut == 503
    assert isinstance(exc.value, Refuse)


async def test_une_cle_lisible_par_d_autres_est_refusee(iam_factice):
    url, cle = iam_factice
    os.chmod(cle, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    with pytest.raises(Exception, match="mode 600"):
        adaptateur(url, cle)
