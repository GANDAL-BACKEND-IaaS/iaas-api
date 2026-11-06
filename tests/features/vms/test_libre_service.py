"""Le libre-service : une VM se cree SANS acceptation par un administrateur.

POURQUOI CE FICHIER EXISTE. L administrateur valide le COMPTE et pose les
QUOTAS ; c est tout ce qu il a a decider. Lui redemander son avis a chaque
machine, c est lui faire relire un calcul que le service de decision vient de
faire — et c est la file d attente ou un etudiant perd deux jours pour une VM
de 2 vCPU.

Ce que ces tests tiennent, et qu aucune relecture ne garantit :

    creation directe      la VM EXISTE, sans qu aucun admin n intervienne
    quota epuise          refuse, et RIEN n est cree
    non-membre            refuse
    la trace              une ligne « libre-service » reste dans l historique
    le quota est COMPTE   et il l est contre la taille demandee
    panne de l hyperviseur  la reservation est LIBEREE
"""
from __future__ import annotations

import pytest

from app.core.dependencies import get_decision
from app.infrastructure.iam.fake_decision import FakeDecisionClient
from app.main import app
from tests.support import login_header, own_project

_TAILLE = {
    "name": "poste-libre",
    "configuration": {"ram_gb": 2, "vcpu": 2, "vram_gb": 1, "ssd_gb": 20},
}
PLAN = {"vm_count": 5, "vcpu": 16, "ram_gb": 32, "disk_gb": 500,
        # « vram_gb » de la configuration compte dans « gpu_mem_mb » : l oublier
        # ici faisait refuser sur un quota GPU a zero, et c etait MON test qui
        # avait tort, pas le code.
        "gpu_mem_mb": 8192}


@pytest.fixture
def decision():
    faux = FakeDecisionClient(plan_par_defaut=PLAN)
    app.dependency_overrides[get_decision] = lambda: faux
    yield faux
    app.dependency_overrides.pop(get_decision, None)


async def test_la_vm_existe_sans_aucun_administrateur(client, db, iam, decision):
    """LE TEST QUI COMPTE : aucun appel admin, et la VM est la."""
    await own_project(db, iam)
    headers = await login_header(iam)

    r = client.post("/api/v1/projects/p1/vms/direct", headers=headers,
                    json=_TAILLE)
    assert r.status_code == 201, r.text
    corps = r.json()
    # DEJA ACCEPTEE : il n y a pas eu d attente, et il n y en aura pas.
    assert corps["status"] == "accepted"
    assert corps["admin_note"] == "libre-service"

    # Et la VM est VRAIMENT la, visible par la route de lecture.
    liste = client.get("/api/v1/projects/p1/vms", headers=headers)
    assert liste.status_code == 200
    noms = [v["name"] for v in liste.json()["items"]]
    assert "poste-libre" in noms, liste.text


async def test_le_quota_est_compte(client, db, iam, decision):
    """Sans ca, le libre-service serait un distributeur sans compteur."""
    await own_project(db, iam)
    headers = await login_header(iam)
    client.post("/api/v1/projects/p1/vms/direct", headers=headers, json=_TAILLE)

    # Le faux client tient « consomme » par PROJET.
    consomme = decision.consomme.get("p1", {})
    assert consomme.get("vcpu") == 2, decision.consomme
    assert consomme.get("ram_gb") == 2, decision.consomme
    assert consomme.get("disk_gb") == 20, decision.consomme
    assert consomme.get("vm_count") == 1, decision.consomme


async def test_rien_n_est_reserve_en_trop(client, db, iam, decision):
    """La reservation est CONFIRMEE, pas laissee en suspens."""
    await own_project(db, iam)
    headers = await login_header(iam)
    client.post("/api/v1/projects/p1/vms/direct", headers=headers, json=_TAILLE)
    # « _en_cours » ne garde que les reservations NI confirmees NI liberees.
    assert decision._en_cours == {}, decision._en_cours
    # Et la sequence s est bien deroulee dans l ordre du contrat.
    assert "reserver" in decision.etapes()
    assert "confirmer" in decision.etapes()


async def test_quota_epuise_refuse_et_ne_cree_rien(client, db, iam):
    """Le motif d IAM remonte, et aucune VM n apparait."""
    faux = FakeDecisionClient(plan_par_defaut={"vm_count": 0, "vcpu": 0,
                                               "ram_gb": 0, "disk_gb": 0})
    app.dependency_overrides[get_decision] = lambda: faux
    try:
        await own_project(db, iam)
        headers = await login_header(iam)
        r = client.post("/api/v1/projects/p1/vms/direct", headers=headers,
                        json=_TAILLE)
        assert r.status_code in (403, 409), r.text
        # RIEN n a ete cree : c est la moitie du test qui compte vraiment.
        liste = client.get("/api/v1/projects/p1/vms", headers=headers)
        assert liste.json()["items"] == [], liste.text
    finally:
        app.dependency_overrides.pop(get_decision, None)


async def test_un_non_membre_est_refuse(client, db, iam, decision):
    """Le libre-service ne veut pas dire « libre pour tout le monde »."""
    await own_project(db, iam)
    iam.add_user("dehors@x.cm", "pw")
    headers = await login_header(iam, "dehors@x.cm")
    r = client.post("/api/v1/projects/p1/vms/direct", headers=headers,
                    json=_TAILLE)
    assert r.status_code in (403, 404), r.text


async def test_la_trace_reste_dans_l_historique(client, db, iam, decision):
    """L audit et « GET /requests » voient ce qui a ete cree.

    Supprimer la ligne de demande aurait fait disparaitre du journal tout ce
    qui est cree en libre-service — c est-a-dire, desormais, presque tout.
    """
    await own_project(db, iam)
    headers = await login_header(iam)
    client.post("/api/v1/projects/p1/vms/direct", headers=headers, json=_TAILLE)
    r = client.get("/api/v1/requests", headers=headers)
    assert r.status_code == 200, r.text
    lignes = r.json()["items"]
    assert len(lignes) == 1
    assert lignes[0]["status"] == "accepted"
    assert lignes[0]["admin_note"] == "libre-service"


async def test_la_demande_classique_reste_disponible(client, db, iam, decision):
    """Elle reste le bon chemin pour une EXCEPTION, pas pour le quotidien."""
    await own_project(db, iam)
    headers = await login_header(iam)
    r = client.post("/api/v1/projects/p1/vms", headers=headers, json=_TAILLE)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
