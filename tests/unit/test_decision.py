"""Le port de décision : la séquence, et surtout ses sorties de secours."""

from __future__ import annotations

import pytest

from app.application.ports.decision import Refuse, ServiceIndisponible
from app.infrastructure.iam.fake_decision import FakeDecisionClient

# `asyncio_mode = "auto"` dans pyproject.toml : les tests async tournent sans
# decoration, comme le reste de la suite.

def client(**kw) -> FakeDecisionClient:
    c = FakeDecisionClient(**kw)
    c.accorder("p-vision", vm_count=2, vcpu=4, ram_gb=8, disk_gb=100)
    return c


# ─── la séquence ────────────────────────────────────────────────────────────

async def test_la_sequence_complete():
    d = client()
    await d.autoriser(sujet="etu-1", action="vm:create",
                      ressource={"type": "vm", "id": "poste-1", "projet": "p-vision"},
                      contexte={"vcpu": 2, "ram_gb": 4, "disk_gb": 20})
    async with d.transaction(sujet="etu-1", projet="p-vision",
                             ressources={"vm_count": 1, "vcpu": 2}) as t:
        await d.confirmer(t, id_ressource="poste-1", type_ressource="vm")
    assert d.etapes() == ["autoriser", "reserver", "confirmer"]
    assert d.consomme["p-vision"] == {"vm_count": 1, "vcpu": 2}


async def test_un_refus_porte_le_motif_et_la_phrase():
    d = client(refuser={"vm:create"})
    with pytest.raises(Refuse) as exc:
        await d.autoriser(sujet="etu-1", action="vm:create",
                          ressource={"type": "vm", "id": "x", "projet": "p-vision"})
    assert exc.value.motif == "politique"
    assert "vm:create" in exc.value.explication
    assert exc.value.statut == 403


async def test_sans_sujet_on_refuse_plutot_que_decider_sur_le_service():
    d = client()
    with pytest.raises(Refuse) as exc:
        await d.autoriser(sujet="", action="vm:create", ressource={"type": "vm", "id": "x"})
    assert exc.value.motif == "sujet_absent"


# ─── les deux fautes qui ne se voient pas ───────────────────────────────────

async def test_si_la_creation_leve_le_quota_est_rendu():
    d = client()
    with pytest.raises(RuntimeError):
        async with d.transaction(sujet="etu-1", projet="p-vision",
                                 ressources={"vm_count": 1, "vcpu": 2}):
            raise RuntimeError("l hyperviseur a refuse")
    assert d.etapes() == ["reserver", "liberer"]
    # Le compteur est revenu a zero : aucun quota fantome.
    assert d.consomme["p-vision"] == {"vm_count": 0, "vcpu": 0}


async def test_sortir_sans_confirmer_libere_aussi():
    """Faute n° 3 : la reservation expirerait, et la ressource existerait."""
    d = client()
    async with d.transaction(sujet="etu-1", projet="p-vision",
                             ressources={"vm_count": 1}):
        pass                                     # on oublie `confirmer`
    assert "liberer" in d.etapes()
    assert d.consomme["p-vision"]["vm_count"] == 0


async def test_une_reservation_confirmee_n_est_pas_liberee():
    d = client()
    async with d.transaction(sujet="etu-1", projet="p-vision",
                             ressources={"vm_count": 1}) as t:
        await d.confirmer(t, id_ressource="poste-1", type_ressource="vm")
    assert "liberer" not in d.etapes()
    assert d.consomme["p-vision"]["vm_count"] == 1


async def test_liberer_ne_leve_jamais():
    """Faire echouer le nettoyage masquerait l erreur d origine."""
    d = client()
    t = await d.reserver(sujet="etu-1", projet="p-vision", ressources={"vm_count": 1})
    await d.liberer(t)
    await d.liberer(t)                           # deux fois : toujours silencieux


# ─── le quota, et le fait que deux requêtes ne passent pas pour une ─────────

async def test_deux_reservations_simultanees_ne_passent_pas_pour_une():
    """Sans reservation, les deux auraient ete autorisees sur la meme place."""
    d = FakeDecisionClient()
    d.accorder("p-petit", vm_count=1)
    await d.reserver(sujet="etu-1", projet="p-petit", ressources={"vm_count": 1})
    with pytest.raises(Refuse) as exc:
        await d.reserver(sujet="etu-2", projet="p-petit", ressources={"vm_count": 1})
    assert exc.value.motif == "quota"
    assert exc.value.statut == 409
    assert "il reste 0 vm_count sur 1" in exc.value.explication


async def test_un_projet_sans_quota_est_refuse_par_defaut():
    """Absence de limite = ZERO pour un projet : on n accorde jamais une
    ressource qu on ne sait pas compter."""
    d = FakeDecisionClient()
    with pytest.raises(Refuse):
        await d.reserver(sujet="etu-1", projet="p-inconnu", ressources={"vm_count": 1})


# ─── le stockage : la porte EST le quota ────────────────────────────────────

async def test_un_projet_sans_quota_de_stockage_ne_peut_pas_en_creer():
    d = FakeDecisionClient()
    d.accorder("p-sans-stockage", vm_count=5)        # des VM, mais pas de stockage
    await d.autoriser(sujet="etu-1", action="storage:bucket:create",
                      ressource={"type": "bucket", "id": "jeux",
                                 "projet": "p-sans-stockage", "fournisseur": "s3"})
    with pytest.raises(Refuse) as exc:
        await d.reserver(sujet="etu-1", projet="p-sans-stockage",
                         ressources={"storage_buckets": 1})
    assert exc.value.motif == "quota"


async def test_accorder_le_quota_active_le_stockage():
    """Il n y a pas d interrupteur separe : accorder, c est activer."""
    d = FakeDecisionClient()
    d.accorder("p-vision", storage_buckets=3, storage_gb=50)
    t = await d.reserver(sujet="etu-1", projet="p-vision",
                         ressources={"storage_buckets": 1})
    await d.confirmer(t, id_ressource="seau-1", type_ressource="bucket")
    assert d.consomme["p-vision"]["storage_buckets"] == 1
    # Le remettre a zero le retire.
    d.accorder("p-vision", storage_buckets=0)
    with pytest.raises(Refuse):
        await d.reserver(sujet="etu-1", projet="p-vision",
                         ressources={"storage_buckets": 1})


async def test_le_fournisseur_voyage_dans_la_ressource_pas_dans_un_quota():
    """« s3 » n est pas une quantite : c est un attribut, lisible par une politique."""
    d = client()
    await d.autoriser(sujet="etu-1", action="storage:bucket:create",
                      ressource={"type": "bucket", "id": "seau", "projet": "p-vision",
                                 "fournisseur": "supabase"})
    _, appel = d.journal[0]
    assert appel["ressource"]["fournisseur"] == "supabase"


# ─── le défaut est le refus ─────────────────────────────────────────────────

async def test_indisponible_est_un_refus():
    """« except Refuse » doit attraper les deux : il n existe aucun chemin ou
    une panne du service rende « autorise »."""
    assert issubclass(ServiceIndisponible, Refuse)
    assert ServiceIndisponible("injoignable").statut == 503
