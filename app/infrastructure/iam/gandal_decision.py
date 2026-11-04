"""Adaptateur réel : `DecisionPort` branché sur le service de décision GANDAL.

IL NE REFAIT PAS LA SEQUENCE. Elle vit dans `gandal_garde`, la bibliothèque du
dépôt GANDAL (`iam/garde-serveur/`), et ce module ne fait que l exposer derrière
le port. Recopier la séquence ici la ferait divergerait de celle du GPUaaS et de
celle du service de stockage, qui devront la suivre aussi — et c est le jour où
elles divergent qu on compte faux.

POURQUOI UN POOL DE FILS. `gandal_garde` est SYNCHRONE et sans dépendance : c est
voulu — les trois hôtes n ont pas de sortie internet, et un service qui exige
`httpx` pour démarrer est un service qu on ne peut pas réparer sur place. Le port,
lui, est asynchrone comme le reste du backend. `anyio.to_thread` fait le pont :
chaque appel part dans un fil, et la boucle d événements n est jamais bloquée par
une attente réseau de cinq secondes.

LE CLIENT EST PARTAGE. Il porte une session de rôle obtenue par
`/sts/assume-role` : en endosser une par requête multiplierait les appels sans
rien gagner. La session est bornée et révocable, c est tout l intérêt.
"""
from __future__ import annotations

import anyio

from app.application.ports.decision import (
    DecisionPort,
    Refuse,
    ServiceIndisponible,
    Transaction,
)

try:
    from gandal_garde import ClientIam, Garde
    from gandal_garde import IamIndisponible as _GardeIndisponible
    from gandal_garde import IamRefuse as _GardeRefus
except ImportError as _e:                                   # pragma: no cover
    # Un message qui dit QUOI FAIRE. « No module named gandal_garde » dans un
    # journal de production n a jamais aidé personne à 3 h du matin.
    raise ImportError(
        "« gandal_garde » est absent. C est la bibliothèque de garde IAM du dépôt "
        "GANDAL, volontairement non publiée sur PyPI :\n"
        "    pip install -e /chemin/vers/Gandal/iam/garde-serveur\n"
        "Pour développer sans IAM, utilisez FakeDecisionClient "
        "(DECISION_BACKEND=fake)."
    ) from _e


def _traduire(e: Exception) -> Refuse:
    """Les exceptions de la bibliothèque deviennent celles du port.

    Le backend ne doit pas dépendre des types de `gandal_garde` : le jour où on
    change de bibliothèque, seul ce fichier bouge.
    """
    if isinstance(e, _GardeIndisponible):
        return ServiceIndisponible(str(e))
    if isinstance(e, _GardeRefus):
        return Refuse(str(e), motif=e.motif, explication=e.explication,
                      statut=e.statut)
    return ServiceIndisponible(f"erreur inattendue du service de decision : {e}")


class GandalDecisionClient(DecisionPort):
    """`DecisionPort` au-dessus de `gandal_garde`."""

    def __init__(self, client: ClientIam) -> None:
        self._client = client
        # PAR INSTANCE, et non en attribut de classe : un dictionnaire de classe
        # serait partagé par tous les clients, et les réservations d un fuiraient
        # dans l autre. Il garde la garde vivante le temps de confirmer ou de
        # libérer — la perdre reviendrait à ne plus pouvoir libérer, la faute n° 4.
        self._gardes: dict[str, Garde] = {}

    # ─── un garde par appel, un client pour tous ────────────────────────────
    #
    # `Garde` ne porte que le sujet, le projet et la réservation en cours : le
    # construire par appel ne coûte rien, et le partager entre deux requêtes
    # mélangerait leurs réservations.
    def _garde(self, sujet: str, projet: str, correlation: str) -> Garde:
        try:
            return Garde(self._client, sujet=sujet, projet=projet,
                         correlation=correlation)
        except Exception as e:
            raise _traduire(e) from e

    async def autoriser(self, *, sujet: str, action: str, ressource: dict,
                        contexte: dict | None = None,
                        correlation: str = "") -> str:
        g = self._garde(sujet, str(ressource.get("projet") or ""), correlation)
        try:
            return await anyio.to_thread.run_sync(
                lambda: g.decider(action, ressource, contexte))
        except Exception as e:
            raise _traduire(e) from e

    async def reserver(self, *, sujet: str, ressources: dict[str, int],
                       projet: str = "", duree_s: int = 900,
                       portee_ressource: str = "",
                       correlation: str = "") -> Transaction:
        g = self._garde(sujet, projet, correlation)
        try:
            await anyio.to_thread.run_sync(
                lambda: g.reserver(ressources, duree_s=duree_s,
                                   portee_ressource=portee_ressource))
        except Exception as e:
            raise _traduire(e) from e
        t = Transaction(reservation=g.reservation, ressources=dict(ressources))
        self._gardes[t.reservation] = g
        return t

    async def confirmer(self, t: Transaction, *, id_ressource: str,
                        type_ressource: str, correlation: str = "") -> None:
        g = self._gardes.get(t.reservation)
        if g is None:
            raise ServiceIndisponible(
                f"reservation « {t.reservation} » inconnue de ce processus : "
                "elle expirera seule, mais la ressource n est pas comptee")
        try:
            await anyio.to_thread.run_sync(
                lambda: g.confirmer(id_ressource, type_ressource))
        except Exception as e:
            raise _traduire(e) from e
        t.confirmee = True
        self._gardes.pop(t.reservation, None)

    async def liberer(self, t: Transaction, *, correlation: str = "") -> None:
        """NE LEVE JAMAIS : `gandal_garde.liberer` avale déjà son échec, et faire
        échouer le nettoyage masquerait l erreur d origine."""
        g = self._gardes.pop(t.reservation, None)
        if g is None or t.confirmee:
            return
        try:
            await anyio.to_thread.run_sync(g.liberer)
        except Exception:                            # noqa: BLE001, S110
            # LE SILENCE EST VOULU, et c est la seule place du module ou il
            # l est. `liberer` est appele depuis le chemin d erreur : si le
            # nettoyage levait, il masquerait l erreur d origine — celle que
            # l appelant doit voir. La reservation expirera d elle-meme.
            pass

    async def redimensionner(self, *, sujet: str, id_ressource: str,
                             quantites: dict[str, int],
                             correlation: str = "") -> None:
        g = self._garde(sujet, "", correlation)
        try:
            await anyio.to_thread.run_sync(
                lambda: g.redimensionner(id_ressource, quantites))
        except Exception as e:
            raise _traduire(e) from e

    async def rendre(self, *, sujet: str, id_ressource: str,
                     correlation: str = "") -> None:
        g = self._garde(sujet, "", correlation)
        try:
            await anyio.to_thread.run_sync(lambda: g.rendre(id_ressource))
        except Exception as e:
            raise _traduire(e) from e
