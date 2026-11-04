"""Port de DECISION et de QUOTA — distinct de `IamPort`, et volontairement.

POURQUOI UN SECOND PORT PLUTOT QU UN AJOUT A `IamPort`. Les deux répondent à des
questions différentes :

    IamPort         « qui es-tu, et quels droits portes-tu sur ce projet ? »
    DecisionPort    « as-tu le droit de faire CECI, MAINTENANT, et reste-t-il
                      du quota pour le faire ? »

La première est une propriété de la personne, stable entre deux requêtes. La
seconde dépend de l action demandée, de sa TAILLE, de l heure, du second facteur,
de l état du projet et de ce qui reste au compteur. Les mélanger obligerait
`get_rights()` à rendre une réponse qui dépend de la requête en cours, ce qui
n est plus un droit mais un verdict.

Et le verdict se paie : il RETIENT du quota. Un port qui lit ne doit pas écrire.

CE PORT N EST PAS UN CONFORT. Sans lui, n importe quel appel direct au backend
crée des ressources que les quotas ne comptent pas, et tout ce qui est déclaré
dans IAM — rôles, attributs, politiques, quotas — ne décide de rien. Le SDK a
bien une garde de son côté, mais un garde-fou dans un client est contournable :
il suffit d appeler le backend directement.

LA SEQUENCE A QUATRE FACONS DE MAL TOURNER ET UNE SEULE JUSTE :

    autoriser → reserver → (le backend crée) → confirmer   ou   liberer

  1. créer sans autoriser    n importe qui fait n importe quoi ;
  2. autoriser sans réserver deux requêtes simultanées passent toutes deux
                             alors qu une seule tient dans le quota ;
  3. créer sans confirmer    la réservation expire, le quota revient, et la
                             ressource existe toujours ;
  4. échouer sans libérer    le quota reste retenu pour une ressource qui n a
                             jamais existé, et la personne est bloquée sans
                             comprendre pourquoi.

Les points 3 et 4 sont les plus coûteux parce qu ils NE SE VOIENT PAS : rien ne
casse, les chiffres mentent. D où `transaction()`, qui confirme ou libère à la
sortie — y compris quand le corps lève.

LE DEFAUT EST LE REFUS. Une panne du service de décision lève `ServiceIndisponible`,
qui HERITE de `Refuse` : `except Refuse` attrape les deux, et il n existe aucun
chemin où une panne rende « autorisé ». Autoriser par défaut ferait de chaque
panne d IAM une levée générale des quotas — au moment précis où personne ne
regarde.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


class Refuse(Exception):
    """La demande est refusée. `motif` est le code rendu par IAM."""

    def __init__(self, message: str, *, motif: str = "", explication: str = "",
                 statut: int = 403) -> None:
        super().__init__(message)
        self.motif, self.explication, self.statut = motif, explication, statut


class ServiceIndisponible(Refuse):
    """Le service de décision n a pas pu répondre. Le défaut reste le refus."""

    def __init__(self, message: str) -> None:
        super().__init__(message, motif="decision_indisponible",
                         explication=message, statut=503)


@dataclass
class Transaction:
    """Une réservation en cours. `confirmer` ou `liberer`, jamais les deux."""

    reservation: str = ""
    confirmee: bool = False
    # Ce qui a été retenu, pour qu un journal puisse le dire sans redemander.
    ressources: dict[str, int] = field(default_factory=dict)


class DecisionPort(ABC):
    """Ce que le backend demande au service de décision, et rien de plus."""

    @abstractmethod
    async def autoriser(self, *, sujet: str, action: str, ressource: dict,
                        contexte: dict | None = None,
                        correlation: str = "") -> str:
        """Pose la question. Lève `Refuse` si c est non.

        `sujet` est la PERSONNE, jamais le service : sans cela la décision
        porterait sur le backend, et tout le monde pourrait ce qu il peut.
        Rend l explication d IAM, bonne à journaliser.
        """

    @abstractmethod
    async def reserver(self, *, sujet: str, ressources: dict[str, int],
                       projet: str = "", duree_s: int = 900,
                       portee_ressource: str = "",
                       correlation: str = "") -> Transaction:
        """Retient le quota avant de créer. Lève `Refuse` s il est épuisé."""

    @abstractmethod
    async def confirmer(self, t: Transaction, *, id_ressource: str,
                        type_ressource: str, correlation: str = "") -> None:
        """La ressource existe : la réservation devient une consommation."""

    @abstractmethod
    async def liberer(self, t: Transaction, *, correlation: str = "") -> None:
        """La création a échoué : le quota revient tout de suite.

        N A PAS LE DROIT DE LEVER. Faire échouer le nettoyage masquerait
        l erreur d origine — celle que l appelant doit voir.
        """

    @abstractmethod
    async def redimensionner(self, *, sujet: str, id_ressource: str,
                             quantites: dict[str, int],
                             correlation: str = "") -> None:
        """La ressource n a plus la meme taille : IAM recalcule le quota.

        LES QUANTITES SONT ABSOLUES, et c est IAM qui soustrait. Lui envoyer
        l ecart reviendrait a faire porter par le backend l arithmetique sur
        laquelle la decision repose — et deux requetes concurrentes
        calculeraient leur ecart sur la meme valeur de depart.

        A ne pas confondre avec `reserver` : une reservation retient de la place
        pour une ressource qui n existe pas encore. Ici elle existe, et on
        corrige ce qu elle occupe.
        """

    @abstractmethod
    async def rendre(self, *, sujet: str, id_ressource: str,
                     correlation: str = "") -> None:
        """La ressource est détruite : son quota revient. Sans cet appel, le
        quota reste consommé par quelque chose qui n existe plus."""

    # ─── le gestionnaire qui empêche les fautes 3 et 4 ──────────────────────

    @asynccontextmanager
    async def transaction(self, *, sujet: str, ressources: dict[str, int],
                          projet: str = "", duree_s: int = 900,
                          portee_ressource: str = "", correlation: str = ""):
        """À utiliser APRES `autoriser`, autour de la création :

            await decision.autoriser(sujet=..., action="vm:create", ...)
            async with decision.transaction(sujet=..., ressources={...}) as t:
                vm = await hyperviseur.creer(...)
                await decision.confirmer(t, id_ressource=vm.id, type_ressource="vm")

        Si le corps lève, la sortie libère. Si `confirmer` a été appelé, elle ne
        touche à rien.
        """
        t = await self.reserver(sujet=sujet, ressources=ressources, projet=projet,
                                duree_s=duree_s, portee_ressource=portee_ressource,
                                correlation=correlation)
        try:
            yield t
        except BaseException:
            await self.liberer(t, correlation=correlation)
            raise
        else:
            if not t.confirmee:
                # Sortie sans confirmation : c est la faute n° 3. On libère, et
                # le quota ne reste pas retenu pour rien. Un oubli de `confirmer`
                # devient une absence de consommation, pas un quota fantôme.
                await self.liberer(t, correlation=correlation)
