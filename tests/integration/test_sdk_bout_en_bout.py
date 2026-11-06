"""Le VRAI SDK contre ce backend, sans serveur et sans bouchon.

POURQUOI CE FICHIER EST LE SEUL QUI PROUVE QUE LE SDK EST UTILISABLE. Les tests
du backend valident SES schemas ; ceux du SDK valident LES SIENS. Personne ne
verifie que les deux coincident — et c est precisement la que les contrats
divergent, en silence, jusqu a ce qu un appelant leve une exception Pydantic en
production.

Ici, le SDK deserialise avec ses propres modeles ce que ce backend a reellement
serialise, par son vrai code de transport. Un champ renomme d un cote fait
echouer ce fichier.

PAS DE SERVEUR : `TestClient` de Starlette EST un `httpx.Client`, et
`HttpTransport` du SDK accepte qu on lui en passe un.

Le fichier s ignore si le SDK n est pas installe :
    pip install -e /chemin/vers/GANDAL-SDK
"""
from __future__ import annotations

import pytest

from app.core.dependencies import get_decision
from app.infrastructure.iam.fake_decision import FakeDecisionClient
from app.main import app
from tests.support import login_header, own_project

gandal_sdk = pytest.importorskip("gandal_sdk", reason="pip install -e <GANDAL-SDK>")

from gandal_sdk._http import HttpTransport  # noqa: E402
from gandal_sdk.errors import GandalApiError  # noqa: E402
from gandal_sdk.orchestration.api import OrchestrationApi  # noqa: E402
from gandal_sdk.orchestration.models import (  # noqa: E402
    VmConfigurationIn,
    VMCreateRequestIn,
)

PLAN = {"vm_count": 5, "vcpu": 16, "ram_gb": 32, "disk_gb": 500, "gpu_mem_mb": 8192}


@pytest.fixture
def decision():
    faux = FakeDecisionClient(plan_par_defaut=PLAN)
    app.dependency_overrides[get_decision] = lambda: faux
    yield faux
    app.dependency_overrides.pop(get_decision, None)


def sdk(client, entetes) -> OrchestrationApi:
    """Un SDK qui parle a l application en memoire, avec un jeton deja obtenu.

    On pose le jeton directement plutot que de passer par `auth.login` : les
    comptes viennent du mock IAM des fixtures, et c est le CONTRAT des reponses
    qu on mesure ici, pas le chemin d authentification — leurs propres tests le
    couvrent deja.
    """
    o = OrchestrationApi(HttpTransport("http://testserver", client=client))
    o._http.set_token(entetes["Authorization"].removeprefix("Bearer "))
    return o


@pytest.mark.anyio
async def test_le_sdk_lit_la_liste_des_projets(client, iam, db, decision):
    await own_project(db, iam, "p1")
    h = await login_header(iam)
    page = sdk(client, h).projects.list()
    # Le SDK valide `Page[ProjectOut]` : une liste nue leverait ici.
    assert page.total_items == 1
    assert page.items[0].id == "p1"
    assert page.items[0].current_user_role in ("owner", "guest")


@pytest.mark.anyio
async def test_le_sdk_lit_les_membres_en_Page(client, iam, db, decision):
    await own_project(db, iam, "p1")
    h = await login_header(iam)
    membres = sdk(client, h).projects.list_members("p1")
    assert membres.total_items >= 1


@pytest.mark.anyio
async def test_le_sdk_depose_une_demande_et_valide_RequestOut(client, iam, db, decision):
    await own_project(db, iam, "p1")
    h = await login_header(iam)
    api = sdk(client, h)
    d = api.vms.request_create("p1", VMCreateRequestIn(
        name="poste-1",
        configuration=VmConfigurationIn(ram_gb=4, vcpu=2, vram_gb=0, ssd_gb=20)))
    assert d.status == "pending" and d.kind == "vm_create"
    # LE POINT : la decision a ete demandee, et AUCUN quota n est retenu.
    assert "autoriser" in decision.etapes()
    assert decision.consomme.get("p1", {}) == {}
    # Et aucune VM n existe encore.
    assert api.vms.list("p1").total_items == 0


@pytest.mark.anyio
async def test_dix_demandes_en_attente_n_epuisent_pas_le_quota(client, iam, db, decision):
    """Le piege que « decider tot, compter tard » ferme."""
    await own_project(db, iam, "p1")
    h = await login_header(iam)
    api = sdk(client, h)
    for i in range(10):
        api.vms.request_create("p1", VMCreateRequestIn(
            name=f"poste-{i}",
            configuration=VmConfigurationIn(ram_gb=4, vcpu=2, vram_gb=0, ssd_gb=20)))
    assert decision.consomme.get("p1", {}) == {}


@pytest.mark.anyio
async def test_un_refus_de_decision_porte_son_motif_jusqu_au_SDK(client, iam, db, decision):
    """« erreur interne » n aide personne ; « quota » et sa phrase, si."""
    await own_project(db, iam, "p1")
    h = await login_header(iam)
    decision.refuser.add("vm:create")
    with pytest.raises(GandalApiError) as exc:
        sdk(client, h).vms.request_create("p1", VMCreateRequestIn(
            name="poste-1",
            configuration=VmConfigurationIn(ram_gb=4, vcpu=2, vram_gb=0, ssd_gb=20)))
    assert exc.value.status == 403
    assert "politique" in str(exc.value).lower() or "vm:create" in str(exc.value)


@pytest.mark.anyio
async def test_sans_service_de_decision_le_sdk_fonctionne_comme_avant(client, iam, db):
    """« off » doit etre INERTE : la greffe ne change rien quand elle est eteinte."""
    app.dependency_overrides.pop(get_decision, None)
    await own_project(db, iam, "p1")
    h = await login_header(iam)
    api = sdk(client, h)
    d = api.vms.request_create("p1", VMCreateRequestIn(
        name="poste-1",
        configuration=VmConfigurationIn(ram_gb=4, vcpu=2, vram_gb=0, ssd_gb=20)))
    assert d.status == "pending"
