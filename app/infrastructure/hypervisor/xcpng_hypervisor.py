"""Adaptateur REEL du port Hyperviseur : XCP-ng, par « gandal-ctl ».

POURQUOI IL APPELLE « gandal-ctl » AU LIEU DE PARLER A XAPI DIRECTEMENT.
Creer une VM conforme demande bien plus qu un « xe vm-clone » : le choix du
depot selon la regle R1 (disque systeme sur flash LOCALE, jamais sur le
stockage partage), l anti-affinite du disque de donnees (R2), l agent invite
(R3), la plage memoire non degeneree (R4), le modele a cloner selon le profil,
la graine cloud-init — comptes, reseau, MTU 1450, confiance en l autorite SSH,
greffons — puis le detachement de cette graine.

Tout cela existe, eprouve, dans « gandal-ctl ». Le reecrire ici mettrait les
regles R1 a R4 en DOUBLE, et deux copies d une regle divergent toujours. Le jour
de la divergence, une VM naitrait sur le mauvais depot — et c est exactement la
panne du 4 novembre.

CE QUE CET ADAPTATEUR FAIT DONC : il traduit le contrat du port en invocations
de « gandal-ctl » et de « xe » sur le coordinateur, et il refuse ce qu il ne
peut pas faire correctement.

L EXECUTEUR EST INJECTE. « executeur » est une fonction qui lance une commande
et rend (code, sortie, erreur). En production c est SSH vers le coordinateur ;
dans les tests c est un faux. Sans cette couture, cet adaptateur ne serait
eprouvable qu avec trois hyperviseurs sous la main — donc jamais.
"""

from __future__ import annotations

import logging
import shlex
from collections.abc import Callable

import anyio

from app.application.ports.hypervisor import (
    ConsoleAccess,
    HypervisorError,
    HypervisorPort,
    HypervisorUnavailable,
    VmRef,
    VmSpec,
)
from app.shared.enums import PowerAction

logger = logging.getLogger(__name__)

# Les profils, avec leurs dimensions : (vcpu, ram mini Gio, ram maxi Gio,
# disque de donnees Gio). C est la MEME table que
# « gandal-ctl/gandal-ctl.conf » [dimensions] et que « config.PROFILS_VM »
# d IAM. Les trois doivent dire la meme chose ; le test croise d IAM le
# verifie de son cote, et « test_profil_exact » le verifie ici.
PROFILS: dict[str, tuple[int, int, int, int]] = {
    "salle": (4, 2, 8, 50),
    "individuelle": (2, 1, 4, 20),
    "individuelle-legere": (1, 1, 2, 10),
    "service": (2, 1, 2, 20),
    "bac-a-sable": (1, 1, 2, 0),
    "dev-suffisante": (2, 2, 5, 20),
    "dev-moyenne": (4, 3, 8, 40),
    "devops-suffisante": (2, 2, 5, 40),
    "devops-moyenne": (4, 4, 10, 80),
    "ia-suffisante": (4, 4, 10, 60),
    "ia-moyenne": (8, 6, 16, 120),
    "admin-suffisante": (2, 2, 5, 20),
    "admin-moyenne": (4, 3, 8, 40),
}

DELAI_CREATION_S = 600.0
DELAI_COURT_S = 60.0


def profil_pour(spec: VmSpec) -> str:
    """Le profil qui correspond EXACTEMENT a cette taille, ou lève.

    PAS D ARRONDI AU PROFIL SUPERIEUR, et c est le point important.
    Arrondir créerait une VM plus grosse que celle qu IAM a comptée : on
    compterait une taille et on en créerait une autre, exactement l erreur que
    le refus « profil ET taille » d IAM existe pour empêcher.

    Lever plutôt qu arrondir rend le refus visible et nomme les profils. Une
    taille hors profil relève d une demande nominative, pas d un arrondi
    silencieux.
    """
    for nom, (vcpu, _mini, maxi, disque) in PROFILS.items():
        if (spec.vcpu, spec.ram_gb, spec.ssd_gb) == (vcpu, maxi, disque):
            return nom
    raise HypervisorError(
        f"aucun profil ne correspond a {spec.vcpu} vCPU, {spec.ram_gb} Gio de "
        f"memoire et {spec.ssd_gb} Gio de disque. Les profils sont : "
        f"{', '.join(sorted(PROFILS))}. Une taille hors profil releve d une "
        f"demande nominative, pas d un arrondi silencieux.")


class XcpNgHypervisor(HypervisorPort):
    """Le vrai hyperviseur, pilote par « gandal-ctl » sur le coordinateur."""

    def __init__(
        self,
        executeur: Callable[[list[str], float], tuple[int, str, str]],
        *,
        hote_par_defaut: str = "emilia",
        reseau_par_defaut: str = "GESTION",
        autorite_ssh: str = "",
        acces: str = "cle+certificat",
        gandal_ctl: str = "gandal-ctl",
    ) -> None:
        self.executeur = executeur
        self.hote = hote_par_defaut
        self.reseau = reseau_par_defaut
        self.autorite_ssh = autorite_ssh
        self.acces = acces
        self.ctl = gandal_ctl

    # ─── la couture ─────────────────────────────────────────────────────────

    async def _lancer(self, argv: list[str], delai: float = DELAI_COURT_S) -> str:
        """Lance une commande sur le coordinateur. Rend sa sortie standard.

        L EXECUTEUR EST SYNCHRONE et part dans un fil : SSH bloque, et bloquer
        la boucle d evenements figerait TOUTES les requetes du backend pendant
        la creation d une VM — dix minutes, dans le pire cas.
        """
        try:
            code, sortie, erreur = await anyio.to_thread.run_sync(
                self.executeur, argv, delai)
        except Exception as e:                                  # noqa: BLE001
            logger.exception("hyperviseur injoignable : %s", shlex.join(argv))
            raise HypervisorUnavailable(f"coordinateur injoignable : {e}") from e
        if code != 0:
            # LA SORTIE D ERREUR EST RELAYEE. « gandal-ctl » nomme ses refus
            # (« R1 : le disque systeme irait sur XOSTOR ») ; les remplacer par
            # « echec de l hyperviseur » coute une demi-journee a qui le lit.
            raise HypervisorError(
                f"« {shlex.join(argv)} » rend {code} : "
                f"{(erreur or sortie).strip()[:600]}")
        return sortie

    async def _xe(self, *args: str, delai: float = DELAI_COURT_S) -> str:
        return (await self._lancer(["xe", *args], delai)).strip()

    async def _uuid_de(self, nom: str) -> str:
        """L UUID d une VM par son nom, ou "" si elle n existe pas."""
        sortie = await self._xe("vm-list", f"name-label={nom}", "--minimal")
        # « --minimal » rend une liste separee par des virgules. DEUX VM DU MEME
        # NOM est un etat qu on refuse plutot que d en choisir une au hasard.
        uuids = [u for u in sortie.split(",") if u]
        if len(uuids) > 1:
            raise HypervisorError(
                f"{len(uuids)} VM portent le nom « {nom} » : refus d en "
                f"choisir une. Les departager a la main d abord.")
        return uuids[0] if uuids else ""

    async def _ip_de(self, uuid: str) -> str | None:
        """L adresse de la VM, si l agent invite l a deja publiee."""
        try:
            champs = await self._xe("vm-param-get", f"uuid={uuid}",
                                    "param-name=networks")
        except HypervisorError:
            return None
        for morceau in champs.split(";"):
            cle, _, valeur = morceau.partition(":")
            if cle.strip() == "0/ip":
                return valeur.strip() or None
        return None

    # ─── le contrat ─────────────────────────────────────────────────────────

    async def create_vm(self, spec: VmSpec) -> VmRef:
        """Cree une VM par « gandal-ctl creer ». REJOUABLE.

        LA REJOUABILITE EST OBTENUE PAR LE NOM, et c est le contrat du port :
        « le meme appel ne cree pas une seconde VM ». Si une VM de ce nom
        existe deja, on rend SA reference au lieu d en creer une autre — ce qui
        arrive pour de vrai quand le reseau coupe entre la creation et la
        reponse, et que l appelant rejoue.
        """
        existante = await self._uuid_de(spec.name)
        if existante:
            logger.info("VM « %s » deja presente (%s) : rien a creer",
                        spec.name, existante)
            return VmRef(existante, await self._ip_de(existante))

        profil = profil_pour(spec)
        argv = [self.ctl, "creer", spec.name,
                "--profil", profil,
                "--hote", self.hote,
                "--reseau", self.reseau,
                "-y"]
        if self.autorite_ssh:
            argv += ["--autorite-ssh", self.autorite_ssh, "--acces", self.acces]
        await self._lancer(argv, DELAI_CREATION_S)

        uuid = await self._uuid_de(spec.name)
        if not uuid:
            # « gandal-ctl » a rendu 0 mais la VM n est pas la : on ne rend pas
            # une reference inventee. Un VmRef vide ferait ecrire une ligne en
            # base pour une VM qui n existe pas.
            raise HypervisorError(
                f"« {self.ctl} creer » a reussi mais aucune VM « {spec.name} » "
                f"n est visible : etat incoherent, ne pas rejouer sans regarder.")
        return VmRef(uuid, await self._ip_de(uuid))

    async def update_vm(self, ref: VmRef, spec: VmSpec) -> None:
        """Change vCPU et memoire. LA VM DOIT ETRE ARRETEE.

        L ORDRE N EST PAS NEGOCIABLE, et l inverser echoue :
          - en AGRANDISSANT, lever « VCPUs-max » d abord ;
          - en REDUISANT, baisser « VCPUs-at-startup » d abord.
        Un plafond sous le demarrage est refuse par XAPI, dans les deux sens.

        LES QUATRE BORNES DE MEMOIRE SE POSENT EN UN SEUL APPEL
        (« vm-memory-limits-set ») : posees une a une, une borne intermediaire
        incoherente fait refuser XAPI — par exemple un maxi sous le mini.
        """
        etat = await self._xe("vm-param-get", f"uuid={ref.vm_id}",
                              "param-name=power-state")
        if etat != "halted":
            raise HypervisorError(
                f"la VM est « {etat} » : vCPU et memoire ne se changent pas a "
                f"chaud. L arreter d abord.")
        actuel_txt = await self._xe("vm-param-get", f"uuid={ref.vm_id}",
                                    "param-name=VCPUs-max")
        try:
            actuel = int(actuel_txt)
        except ValueError:
            actuel = 0
        if spec.vcpu >= actuel:
            await self._xe("vm-param-set", f"uuid={ref.vm_id}",
                           f"VCPUs-max={spec.vcpu}")
            await self._xe("vm-param-set", f"uuid={ref.vm_id}",
                           f"VCPUs-at-startup={spec.vcpu}")
        else:
            await self._xe("vm-param-set", f"uuid={ref.vm_id}",
                           f"VCPUs-at-startup={spec.vcpu}")
            await self._xe("vm-param-set", f"uuid={ref.vm_id}",
                           f"VCPUs-max={spec.vcpu}")

        # R4 : la memoire est une PLAGE, jamais un nombre. A mini == maxi, le
        # controle dynamique est inerte et la memoire reste reservee en dur ; a
        # 8 Gio figes par VM, le grid tient dix-neuf machines au lieu de
        # quatre-vingt-dix. Le mini vaut 40 % du maxi, comme les profils.
        maxi = spec.ram_gb
        mini = max(1, round(maxi * 0.4))
        await self._xe(
            "vm-memory-limits-set", f"uuid={ref.vm_id}",
            f"static-min={mini}GiB", f"dynamic-min={mini}GiB",
            f"dynamic-max={maxi}GiB", f"static-max={maxi}GiB")

    async def power(self, ref: VmRef, action: PowerAction) -> None:
        """Demarre, arrete ou redemarre. IDEMPOTENT quand c est possible."""
        etat = await self._xe("vm-param-get", f"uuid={ref.vm_id}",
                              "param-name=power-state")
        if action == PowerAction.START:
            # DEJA DEMARREE : on ne fait rien et on ne leve pas. Le port promet
            # des appels rejouables, et « vm-start » sur une VM qui tourne est
            # une erreur XAPI qui remonterait en 503.
            if etat == "running":
                return
            await self._xe("vm-start", f"uuid={ref.vm_id}", delai=120.0)
        elif action == PowerAction.STOP:
            if etat == "halted":
                return
            # « vm-shutdown » demande l arret PROPRE a l agent invite. Sans
            # « --force », une VM qui ignore la demande reste allumee — et c est
            # preferable a un arret brutal qui corrompt son systeme de fichiers.
            await self._xe("vm-shutdown", f"uuid={ref.vm_id}", delai=180.0)
        elif action == PowerAction.RESTART:
            if etat != "running":
                raise HypervisorError(
                    f"la VM est « {etat} » : un redemarrage n a pas de sens. "
                    f"La demarrer.")
            await self._xe("vm-reboot", f"uuid={ref.vm_id}", delai=180.0)
        else:
            raise HypervisorError(f"action inconnue : {action}")

    async def console(self, ref: VmRef) -> ConsoleAccess:
        """L emplacement de la console RFB, tel que XAPI le publie.

        LE BACKEND N ETABLIT PAS LA CONNEXION (F5) : il rend l emplacement, et
        c est au client de s y connecter avec son jeton. Cet adaptateur ne
        fabrique donc aucun jeton ici.
        """
        sortie = await self._xe("console-list", f"vm-uuid={ref.vm_id}",
                                "params=location", "--minimal")
        emplacement = sortie.split(",")[0].strip()
        if not emplacement:
            raise HypervisorError(
                "aucune console publiee pour cette VM : elle est peut-etre "
                "arretee.")
        return ConsoleAccess(url=emplacement, expires_in=300)

    async def delete_vm(self, ref: VmRef) -> None:
        """Detruit la VM. REJOUABLE si elle est deja absente."""
        try:
            etat = await self._xe("vm-param-get", f"uuid={ref.vm_id}",
                                  "param-name=power-state")
        except HypervisorError:
            # DEJA ABSENTE : le contrat dit rejouable, donc on rend sans lever.
            logger.info("VM %s deja absente : rien a detruire", ref.vm_id)
            return
        if etat != "halted":
            # ON ARRETE AVANT DE DETRUIRE. « vm-destroy » sur une VM qui tourne
            # est refuse par XAPI, et un « --force » ici detruirait une VM que
            # quelqu un utilise peut-etre a cet instant.
            await self._xe("vm-shutdown", f"uuid={ref.vm_id}", delai=180.0)
        await self._xe("vm-destroy", f"uuid={ref.vm_id}", delai=120.0)
