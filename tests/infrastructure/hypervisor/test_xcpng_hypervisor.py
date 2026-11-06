"""L adaptateur XCP-ng, eprouve SANS hyperviseur.

L executeur est injecte : ces tests mesurent les COMMANDES que l adaptateur
lance et l ORDRE dans lequel il les lance — ce qui est exactement ce qui casse
en vrai. Un adaptateur qu on ne peut eprouver qu avec trois hyperviseurs sous
la main n est jamais eprouve.
"""

from __future__ import annotations

import pytest

from app.application.ports.hypervisor import (
    HypervisorError,
    HypervisorUnavailable,
    VmRef,
    VmSpec,
)
from app.infrastructure.hypervisor.xcpng_hypervisor import (
    PROFILS,
    XcpNgHypervisor,
    profil_pour,
)
from app.shared.enums import PowerAction

UUID = "d65467f5-c28b-5b9c-b190-67783b20068b"
# « dev-moyenne » : 4 vCPU, 3 -> 8 Gio, 40 Gio
SPEC = VmSpec(name="poste-1", ram_gb=8, vcpu=4, vram_gb=0, ssd_gb=40)


class FauxCoordinateur:
    """Rejoue des reponses, et garde la trace de ce qui a ete lance."""

    def __init__(self, reponses: dict[str, tuple[int, str, str]] | None = None):
        self.reponses = reponses or {}
        self.lancees: list[list[str]] = []
        self.defaut = (0, "", "")

    def __call__(self, argv: list[str], delai: float) -> tuple[int, str, str]:
        self.lancees.append(list(argv))
        for motif, reponse in self.reponses.items():
            if all(m in " ".join(argv) for m in motif.split("|")):
                return reponse
        return self.defaut

    def commandes(self) -> list[str]:
        return [" ".join(a) for a in self.lancees]


def hyp(faux: FauxCoordinateur, **kw) -> XcpNgHypervisor:
    return XcpNgHypervisor(faux, **kw)


# ─── le profil ───────────────────────────────────────────────────────────────

def test_profil_exact():
    assert profil_pour(SPEC) == "dev-moyenne"
    assert profil_pour(VmSpec("x", 16, 8, 0, 120)) == "ia-moyenne"
    assert profil_pour(VmSpec("x", 2, 1, 0, 0)) == "bac-a-sable"


def test_une_taille_hors_profil_est_REFUSEE_pas_arrondie():
    """Arrondir creerait une VM plus grosse que celle qu IAM a comptee.

    C est exactement l erreur que le refus « profil ET taille » d IAM existe
    pour empecher : compter une taille et en creer une autre.
    """
    with pytest.raises(HypervisorError) as e:
        profil_pour(VmSpec("x", ram_gb=7, vcpu=3, vram_gb=0, ssd_gb=35))
    assert "aucun profil" in str(e.value)
    # LE REFUS NOMME LES PROFILS : un « non » muet coute une demi-journee.
    assert "dev-moyenne" in str(e.value)


def test_la_table_des_profils_est_celle_de_gandal_ctl():
    """Trois copies existent — gandal-ctl.conf, IAM, ici. Elles doivent dire
    la meme chose, sinon on compte un quota pour une VM d une autre taille."""
    assert PROFILS["devops-moyenne"] == (4, 4, 10, 80)
    assert PROFILS["ia-moyenne"] == (8, 6, 16, 120)
    assert PROFILS["dev-suffisante"] == (2, 2, 5, 20)


# ─── creation ────────────────────────────────────────────────────────────────

async def test_create_appelle_gandal_ctl_avec_le_profil():
    faux = FauxCoordinateur({
        "vm-list|poste-1": (0, "", ""),          # absente au premier appel
    })
    # Apres « creer », « vm-list » doit rendre l UUID : on change la reponse.
    appels = {"n": 0}

    def executeur(argv, delai):
        faux.lancees.append(list(argv))
        texte = " ".join(argv)
        if "vm-list" in texte:
            appels["n"] += 1
            return (0, UUID if appels["n"] > 1 else "", "")
        if "param-name=networks" in texte:
            return (0, "0/ip: 10.30.0.44; 0/ipv4/0: 10.30.0.44", "")
        return (0, "", "")

    h = XcpNgHypervisor(executeur, autorite_ssh="/etc/ssh/autorite.pub")
    ref = await h.create_vm(SPEC)

    creer = [c for c in faux.commandes() if "creer" in c]
    assert len(creer) == 1, faux.commandes()
    assert "--profil dev-moyenne" in creer[0], creer[0]
    assert "--autorite-ssh /etc/ssh/autorite.pub" in creer[0]
    assert ref.vm_id == UUID
    assert ref.ip_address == "10.30.0.44"


async def test_create_est_REJOUABLE():
    """Le contrat du port : « le meme appel ne cree pas une seconde VM ».

    Ca arrive pour de vrai : le reseau coupe entre la creation et la reponse,
    et l appelant rejoue.
    """
    faux = FauxCoordinateur({"vm-list": (0, UUID, "")})
    h = hyp(faux)
    ref = await h.create_vm(SPEC)
    assert ref.vm_id == UUID
    assert not [c for c in faux.commandes() if "creer" in c], faux.commandes()


async def test_deux_VM_du_meme_nom_sont_refusees():
    """Refus plutot que d en choisir une au hasard."""
    faux = FauxCoordinateur({"vm-list": (0, f"{UUID},autre-uuid", "")})
    with pytest.raises(HypervisorError) as e:
        await hyp(faux).create_vm(SPEC)
    assert "refus d en choisir" in str(e.value)


async def test_creation_qui_reussit_sans_VM_visible_est_une_erreur():
    """« gandal-ctl » rend 0 mais rien n existe : on ne rend pas une reference
    inventee, qui ferait ecrire une ligne en base pour une VM absente."""
    faux = FauxCoordinateur({"vm-list": (0, "", "")})
    with pytest.raises(HypervisorError) as e:
        await hyp(faux).create_vm(SPEC)
    assert "incoherent" in str(e.value)


async def test_le_refus_de_gandal_ctl_est_RELAYE():
    """« R1 : le disque systeme irait sur XOSTOR » doit arriver a l appelant."""
    def executeur(argv, delai):
        if "creer" in " ".join(argv):
            return (2, "", "ARRET - R1 : le disque systeme irait sur XOSTOR")
        return (0, "", "")

    with pytest.raises(HypervisorError) as e:
        await XcpNgHypervisor(executeur).create_vm(SPEC)
    assert "R1" in str(e.value)
    assert "XOSTOR" in str(e.value)


async def test_un_coordinateur_injoignable_donne_UNAVAILABLE():
    """Et pas HypervisorError : l appelant doit pouvoir distinguer « reessaie »
    de « ne reessaie pas »."""
    def executeur(argv, delai):
        raise OSError("connexion refusee")

    with pytest.raises(HypervisorUnavailable):
        await XcpNgHypervisor(executeur).create_vm(SPEC)


# ─── modification : l ordre, qui est tout ────────────────────────────────────

async def test_agrandir_leve_le_PLAFOND_d_abord():
    faux = FauxCoordinateur({
        "param-name=power-state": (0, "halted", ""),
        "param-name=VCPUs-max": (0, "2", ""),
    })
    await hyp(faux).update_vm(VmRef(UUID), SPEC)
    ordre = [c for c in faux.commandes() if "VCPUs" in c and "param-set" in c]
    assert "VCPUs-max=4" in ordre[0], ordre
    assert "VCPUs-at-startup=4" in ordre[1], ordre


async def test_reduire_baisse_le_DEMARRAGE_d_abord():
    """L inverser echoue : un plafond sous le demarrage est refuse par XAPI."""
    faux = FauxCoordinateur({
        "param-name=power-state": (0, "halted", ""),
        "param-name=VCPUs-max": (0, "8", ""),
    })
    await hyp(faux).update_vm(VmRef(UUID), SPEC)
    ordre = [c for c in faux.commandes() if "VCPUs" in c and "param-set" in c]
    assert "VCPUs-at-startup=4" in ordre[0], ordre
    assert "VCPUs-max=4" in ordre[1], ordre


async def test_les_quatre_bornes_memoire_en_UN_SEUL_appel():
    """Posees une a une, une borne intermediaire incoherente fait refuser XAPI."""
    faux = FauxCoordinateur({
        "param-name=power-state": (0, "halted", ""),
        "param-name=VCPUs-max": (0, "4", ""),
    })
    await hyp(faux).update_vm(VmRef(UUID), SPEC)
    limites = [c for c in faux.commandes() if "memory-limits-set" in c]
    assert len(limites) == 1, faux.commandes()
    for borne in ("static-min", "dynamic-min", "dynamic-max", "static-max"):
        assert borne in limites[0]


async def test_R4_la_memoire_reste_une_PLAGE():
    """A mini == maxi le controle dynamique est inerte et la memoire est
    reservee en dur : le grid tient dix-neuf VM au lieu de quatre-vingt-dix."""
    faux = FauxCoordinateur({
        "param-name=power-state": (0, "halted", ""),
        "param-name=VCPUs-max": (0, "4", ""),
    })
    await hyp(faux).update_vm(VmRef(UUID), SPEC)
    limites = [c for c in faux.commandes() if "memory-limits-set" in c][0]
    assert "static-min=3GiB" in limites, limites
    assert "static-max=8GiB" in limites, limites


async def test_modifier_une_VM_ALLUMEE_est_refuse():
    faux = FauxCoordinateur({"param-name=power-state": (0, "running", "")})
    with pytest.raises(HypervisorError) as e:
        await hyp(faux).update_vm(VmRef(UUID), SPEC)
    assert "a chaud" in str(e.value)


# ─── allumage ────────────────────────────────────────────────────────────────

async def test_demarrer_une_VM_DEJA_allumee_ne_fait_rien():
    """« vm-start » sur une VM qui tourne est une erreur XAPI, qui remonterait
    en 503 — alors que le port promet des appels rejouables."""
    faux = FauxCoordinateur({"param-name=power-state": (0, "running", "")})
    await hyp(faux).power(VmRef(UUID), PowerAction.START)
    assert not [c for c in faux.commandes() if "vm-start" in c]


async def test_arreter_une_VM_DEJA_arretee_ne_fait_rien():
    faux = FauxCoordinateur({"param-name=power-state": (0, "halted", "")})
    await hyp(faux).power(VmRef(UUID), PowerAction.STOP)
    assert not [c for c in faux.commandes() if "vm-shutdown" in c]


async def test_l_arret_est_PROPRE_jamais_force():
    """Un arret brutal corrompt le systeme de fichiers de la VM. Une VM qui
    ignore la demande reste allumee, et c est preferable."""
    faux = FauxCoordinateur({"param-name=power-state": (0, "running", "")})
    await hyp(faux).power(VmRef(UUID), PowerAction.STOP)
    arret = [c for c in faux.commandes() if "vm-shutdown" in c]
    assert len(arret) == 1
    assert "--force" not in arret[0]


async def test_redemarrer_une_VM_arretee_est_refuse():
    faux = FauxCoordinateur({"param-name=power-state": (0, "halted", "")})
    with pytest.raises(HypervisorError) as e:
        await hyp(faux).power(VmRef(UUID), PowerAction.RESTART)
    assert "demarrer" in str(e.value)


# ─── console ─────────────────────────────────────────────────────────────────

async def test_la_console_rend_l_emplacement_publie_par_XAPI():
    faux = FauxCoordinateur({
        "console-list": (0, "https://192.168.123.100/console?ref=OpaqueRef:1", ""),
    })
    acces = await hyp(faux).console(VmRef(UUID))
    assert acces.url.startswith("https://192.168.123.100/console")


async def test_pas_de_console_publiee_leve():
    faux = FauxCoordinateur({"console-list": (0, "", "")})
    with pytest.raises(HypervisorError) as e:
        await hyp(faux).console(VmRef(UUID))
    assert "arretee" in str(e.value)


# ─── destruction ─────────────────────────────────────────────────────────────

async def test_detruire_ARRETE_d_abord():
    """« vm-destroy » sur une VM qui tourne est refuse par XAPI, et un
    « --force » detruirait une VM que quelqu un utilise peut-etre."""
    faux = FauxCoordinateur({"param-name=power-state": (0, "running", "")})
    await hyp(faux).delete_vm(VmRef(UUID))
    cmds = faux.commandes()
    assert any("vm-shutdown" in c for c in cmds), cmds
    assert any("vm-destroy" in c for c in cmds), cmds
    assert cmds.index([c for c in cmds if "vm-shutdown" in c][0]) < \
           cmds.index([c for c in cmds if "vm-destroy" in c][0])


async def test_detruire_une_VM_DEJA_absente_est_REJOUABLE():
    def executeur(argv, delai):
        if "param-name=power-state" in " ".join(argv):
            return (1, "", "The uuid you supplied was invalid")
        return (0, "", "")

    # Ne leve pas : le contrat dit rejouable.
    await XcpNgHypervisor(executeur).delete_vm(VmRef(UUID))
