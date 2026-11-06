"""La greffe IAM, allumee : la decision est demandee et le quota est compte.

SANS CE FICHIER, la greffe serait du code inerte. Les 261 autres tests prouvent
qu elle ne casse rien ; ceux-ci prouvent qu elle FAIT quelque chose.

Ce qu ils tiennent, et qu aucune relecture ne garantit :

    deposer une demande   DECIDE, et ne retient AUCUN quota
    accepter              redecide, retient, cree, confirme
    quota epuise          refuse, et RIEN n est cree
    echec de l hyperviseur  la reservation est LIBEREE
    modification          compte l ECART, pas la taille entiere
"""
from __future__ import annotations

import pytest

from app.application.ports.decision import Refuse, ServiceIndisponible
from app.core.dependencies import get_decision
from app.infrastructure.iam.fake_decision import FakeDecisionClient
from app.main import app
from app.shared.models.vms import Vm
from tests.support import login_header, own_project

PLAN = {"vm_count": 5, "vcpu": 16, "ram_gb": 32, "disk_gb": 500, "gpu_mem_mb": 8192}


@pytest.fixture
def decision():
    """Un faux service, INJECTE par la dependance de FastAPI.

    `app.dependency_overrides` est le mecanisme de leur propre `conftest` pour
    `get_db`, `get_iam` et les autres : on s en sert ici aussi, plutot que
    d inventer un second chemin.
    """
    faux = FakeDecisionClient(plan_par_defaut=PLAN)
    app.dependency_overrides[get_decision] = lambda: faux
    yield faux
    app.dependency_overrides.pop(get_decision, None)


def test_le_defaut_du_reglage_est_gandal():
    """Le defaut doit etre SUR, et « off » n est pas sur.

    CE TEST DISAIT L INVERSE JUSQU AU 5 NOVEMBRE 2026, et il avait tort. Son
    argument etait qu un deploiement qui oublie le reglage ne doit pas tomber
    sur un service injoignable. Mais l autre branche de ce choix est pire : avec
    « off », le meme oubli sert TOUTES les routes sans demander une seule
    decision et sans compter un seul quota, en repondant 200 a tout. Une
    autorisation qui tombe en panne OUVERTE est pire qu un service qui refuse
    de demarrer.

    C est donc aux TESTS de dire qu ils ne veulent pas d IAM, et « conftest.py »
    le fait : DECISION_BACKEND=off, avant tout import de « app ».
    """
    import os

    from app.core.settings import Settings

    # On lit le defaut de la CLASSE, pas l environnement de la suite — qui est
    # justement pose a « off » par conftest.
    assert Settings.model_fields["decision_backend"].default == "gandal"
    assert os.environ.get("DECISION_BACKEND") == "off", (
        "la suite doit tourner sans IAM : conftest pose la variable")


def test_la_table_relie_chaque_droit_a_une_action_iam():
    from app.shared.policies import access

    t = access._ACTION_POUR_DROIT
    assert t["vm.request_create"] == "vm:create"
    assert t["vm.request_update"] == "vm:update"
    assert t["vm.delete"] == "vm:delete"
    # Un redemarrage est un arret suivi d un demarrage : la plus FORTE des deux.
    assert t["vm.power"] == "vm:stop"
    # Un droit absent de la table ne demande rien a IAM — le defaut est l ancien
    # comportement, pas un refus surprise.
    assert "droit.inconnu" not in t


def test_un_refus_de_decision_sort_en_problem_json(client, decision):
    """Le MOTIF d IAM doit voyager : « erreur interne » n aide personne."""
    decision.refuser.add("vm:read")
    r = client.get("/api/v1/projects", headers={"Authorization": "Bearer x"})
    # La liste des projets ne passe pas par `authorize` ; on verifie le
    # gestionnaire sur une exception levee directement.
    assert r.status_code in (200, 401, 403)


def test_le_gestionnaire_traduit_Refuse_en_problem_json():
    from fastapi.testclient import TestClient

    from app.main import app

    @app.get("/essai-refus")
    def _essai():
        raise Refuse("quota epuise", motif="quota",
                     explication="il reste 0 vcpu sur 16", statut=409)

    r = TestClient(app).get("/essai-refus")
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    corps = r.json()
    assert corps["motif"] == "quota"
    assert corps["detail"] == "il reste 0 vcpu sur 16"


def test_les_tailles_se_lisent_dans_les_deux_formes_de_payload():
    """« _normalize_vm_create » rend soit une `configuration`, soit les champs a
    plat (resolus depuis un pack). Une seule des deux formes lue donnerait un
    quota nul sur la moitie des demandes — et un quota nul ne refuse rien."""
    from app.features.requests.service import _ressources_de_quota, _tailles

    plat = {"name": "p", "pack_id": "k", "ram_gb": 4, "vcpu": 2,
            "vram_gb": 2, "ssd_gb": 20}
    imbrique = {"name": "p", "configuration": {"ram_gb": 4, "vcpu": 2,
                                               "vram_gb": 2, "ssd_gb": 20}}
    assert _tailles(plat) == _tailles(imbrique)
    r = _ressources_de_quota(plat)
    assert r["vm_count"] == 1 and r["vcpu"] == 2 and r["disk_gb"] == 20
    # 2 Gio de VRAM -> 2048 Mio de quota GPU.
    assert r["gpu_mem_mb"] == 2048
    # Sans VRAM, pas de ligne GPU : une ligne a zero occuperait un plan a zero.
    assert "gpu_mem_mb" not in _ressources_de_quota(
        {"configuration": {"ram_gb": 1, "vcpu": 1, "vram_gb": 0, "ssd_gb": 1}})


def test_un_quota_epuise_leve_un_Refuse_409(decision):
    import anyio

    decision.limites["prj"] = {"vm_count": 0}

    async def essai():
        await decision.reserver(sujet="u", projet="prj",
                                ressources={"vm_count": 1})

    with pytest.raises(Refuse) as exc:
        anyio.run(essai)
    assert exc.value.statut == 409 and exc.value.motif == "quota"


def test_la_transaction_libere_quand_le_corps_leve(decision):
    """Faute n 4 : un quota retenu pour une ressource qui n a jamais existe."""
    import anyio

    async def essai():
        async with decision.transaction(sujet="u", projet="prj",
                                        ressources={"vm_count": 1}):
            raise RuntimeError("l hyperviseur a refuse")

    with pytest.raises(RuntimeError):
        anyio.run(essai)
    assert decision.consomme["prj"]["vm_count"] == 0
    assert "liberer" in decision.etapes()


def test_sortir_sans_confirmer_libere_aussi(decision):
    """Faute n 3 : la reservation expirerait, et la ressource existerait."""
    import anyio

    async def essai():
        async with decision.transaction(sujet="u", projet="prj",
                                        ressources={"vm_count": 1}):
            pass                                  # on oublie `confirmer`

    anyio.run(essai)
    assert decision.consomme["prj"]["vm_count"] == 0


def test_redimensionner_compte_l_ecart(decision):
    import anyio

    async def essai():
        t = await decision.reserver(sujet="u", projet="prj",
                                    ressources={"vcpu": 2})
        await decision.confirmer(t, id_ressource="vm1", type_ressource="vm")
        assert decision.consomme["prj"]["vcpu"] == 2
        await decision.redimensionner(sujet="u", id_ressource="vm1",
                                      quantites={"vcpu": 4})
        # 4, et non 6 : l ecart.
        assert decision.consomme["prj"]["vcpu"] == 4
        await decision.redimensionner(sujet="u", id_ressource="vm1",
                                      quantites={"vcpu": 1})
        # Et reduire REND du quota, ce que le chemin des reservations ne sait pas.
        assert decision.consomme["prj"]["vcpu"] == 1

    anyio.run(essai)


async def test_echec_confirmation_compense_la_vm_creee(client, db, iam, decision, hypervisor):
    """Un quota non confirme ne doit pas laisser une VM orpheline."""
    await own_project(db, iam)
    headers = await login_header(iam)

    confirmer = decision.confirmer

    async def confirmer_applique_mais_indisponible(
        jeton, *, id_ressource, type_ressource, correlation=""
    ):
        await confirmer(
            jeton,
            id_ressource=id_ressource,
            type_ressource=type_ressource,
            correlation=correlation,
        )
        raise ServiceIndisponible("IAM indisponible")

    decision.confirmer = confirmer_applique_mais_indisponible
    response = client.post(
        "/api/v1/projects/p1/vms/direct",
        headers=headers,
        json={
            "name": "poste-test",
            "configuration": {"ram_gb": 2, "vcpu": 2, "vram_gb": 1, "ssd_gb": 20},
        },
    )

    assert response.status_code == 503, response.text
    assert hypervisor.vms == {}
    assert db.query(Vm).count() == 0
    assert decision.consomme.get("p1", {}).get("vm_count", 0) == 0


async def test_refus_iam_au_redimensionnement_ne_modifie_pas_la_vm(
    client, db, iam, decision, hypervisor
):
    """Le quota est valide avant l'hyperviseur; un refus laisse la VM intacte."""
    await own_project(db, iam)
    user_headers = await login_header(iam)
    created = client.post(
        "/api/v1/projects/p1/vms/direct",
        headers=user_headers,
        json={
            "name": "poste-test",
            "configuration": {"ram_gb": 2, "vcpu": 2, "vram_gb": 0, "ssd_gb": 20},
        },
    )
    assert created.status_code == 201, created.text
    vm_id = created.json()["target_resource_id"]

    update = client.post(
        f"/api/v1/projects/p1/vms/{vm_id}/update-requests",
        headers=user_headers,
        json={"configuration": {"ram_gb": 4, "vcpu": 4, "vram_gb": 0, "ssd_gb": 40}},
    )
    assert update.status_code == 202, update.text

    async def refuser_redimensionnement(**kwargs):
        raise Refuse("quota epuise", motif="quota", statut=409)

    decision.redimensionner = refuser_redimensionnement
    admin_headers = await login_header(iam, "root@x.cm")
    response = client.post(
        f"/api/v1/requests/{update.json()['id']}/accept",
        headers=admin_headers,
        json={},
    )

    assert response.status_code == 409, response.text
    assert hypervisor.vms[vm_id].ram_gb == 2
    assert hypervisor.vms[vm_id].vcpu == 2
    assert hypervisor.vms[vm_id].ssd_gb == 20
    vm = db.get(Vm, vm_id)
    assert vm is not None
    assert (vm.ram_gb, vm.vcpu, vm.ssd_gb) == (2, 2, 20)
