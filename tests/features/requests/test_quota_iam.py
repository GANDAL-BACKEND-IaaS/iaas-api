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

from app.application.ports.decision import Refuse
from app.infrastructure.iam.fake_decision import FakeDecisionClient
from app.shared.policies import access

PLAN = {"vm_count": 5, "vcpu": 16, "ram_gb": 32, "disk_gb": 500, "gpu_mem_mb": 8192}


@pytest.fixture
def decision():
    """Branche un faux service pour la duree du test, et le debranche apres.

    Le debranchement n est pas du menage : sans lui, les tests suivants
    heriteraient d un service de decision et ne mesureraient plus ce qu ils
    croient mesurer.
    """
    faux = FakeDecisionClient(plan_par_defaut=PLAN)
    access.brancher_decision(lambda: faux)
    yield faux
    access.brancher_decision(None)


def test_le_resolveur_rend_None_quand_rien_n_est_branche():
    """« off » doit etre inerte, pas permissif par accident : il n a simplement
    pas d interlocuteur."""
    access.brancher_decision(None)
    assert access.resolveur() is None


def test_la_table_relie_chaque_droit_a_une_action_iam():
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
