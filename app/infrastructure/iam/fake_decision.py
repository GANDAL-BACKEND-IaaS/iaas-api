"""`DecisionPort` en mémoire, pour développer et tester sans service de décision.

IL REFUSE POUR DE VRAI. Un faux qui dit toujours « oui » ne vérifie rien : la
première fois que le vrai service refuse, personne n a jamais vu le chemin de
refus s exécuter. Celui-ci tient de vrais compteurs, refuse quand le quota est
épuisé, et sait refuser une action sur commande.

IL N EST PAS UN CONTROLE. `DECISION_BACKEND=fake` est pour le développement.
En production c est `GandalDecisionClient`, et le défaut des réglages est
`gandal` précisément pour qu on ne se retrouve pas en production avec le faux
sans l avoir décidé.
"""
from __future__ import annotations

from app.application.ports.decision import DecisionPort, Refuse, Transaction


class FakeDecisionClient(DecisionPort):
    """Quotas en mémoire. `limites` est par projet, puis par ressource."""

    def __init__(self, *, limites: dict[str, dict[str, int]] | None = None,
                 refuser: set[str] | None = None,
                 tout_permettre: bool = False,
                 plan_par_defaut: dict[str, int] | None = None) -> None:
        # LE PLAN PAR DEFAUT N EST PAS « illimite ». Il est accorde a tout projet
        # dont on n a rien dit, parce qu autrement le mode « fake » refuse tout et
        # ne sert a personne. Les tests qui portent sur les PLAFONDS passent
        # `limites` et laissent celui-ci vide, pour mesurer ce qu ils mesurent.
        self.plan_par_defaut = dict(plan_par_defaut or {})
        self.limites = {p: dict(r) for p, r in (limites or {}).items()}
        self.refuser = set(refuser or ())
        # `tout_permettre` ne lève pas les quotas : il ne lève que les décisions.
        # Les deux portes restent distinctes, comme dans le vrai.
        self.tout_permettre = tout_permettre
        self.consomme: dict[str, dict[str, int]] = {}
        self.journal: list[tuple[str, dict]] = []
        self._suivant = 0
        self._en_cours: dict[str, tuple[str, dict[str, int]]] = {}
        # Ce que chaque ressource occupe, pour que `redimensionner` puisse
        # calculer un ECART — comme le vrai service, qui le lit dans
        # `ressource.quantites`.
        self.tailles: dict[str, dict[str, int]] = {}
        self.projet_de: dict[str, str] = {}

    # ─── décision ───────────────────────────────────────────────────────────

    async def autoriser(self, *, sujet: str, action: str, ressource: dict,
                        contexte: dict | None = None, correlation: str = "") -> str:
        self.journal.append(("autoriser", {"sujet": sujet, "action": action,
                                           "ressource": ressource,
                                           "contexte": contexte or {}}))
        if not sujet:
            raise Refuse("aucun sujet : la decision porterait sur le service",
                         motif="sujet_absent", statut=400)
        if action in self.refuser and not self.tout_permettre:
            raise Refuse(f"« {action} » refuse pour « {sujet} »", motif="politique",
                         explication=f"aucune politique n accorde « {action} »")
        return f"faux service : « {action} » accorde a « {sujet} »"

    # ─── quota ──────────────────────────────────────────────────────────────

    def _restant(self, projet: str, cle: str) -> int:
        # ABSENCE DE LIMITE = ZERO pour un projet, comme dans le vrai service.
        # « On n accorde jamais une ressource qu on ne sait pas compter. »
        plan = self.limites.get(projet) or self.plan_par_defaut
        limite = plan.get(cle, 0)
        return limite - self.consomme.get(projet, {}).get(cle, 0)

    async def reserver(self, *, sujet: str, ressources: dict[str, int],
                       projet: str = "", duree_s: int = 900,
                       portee_ressource: str = "", correlation: str = "") -> Transaction:
        self.journal.append(("reserver", {"sujet": sujet, "projet": projet,
                                          "ressources": dict(ressources),
                                          "portee": portee_ressource}))
        for cle, quantite in ressources.items():
            if quantite and self._restant(projet, cle) < quantite:
                raise Refuse(
                    f"quota « {cle} » epuise pour le projet « {projet} »",
                    motif="quota",
                    explication=f"il reste {max(0, self._restant(projet, cle))} "
                                f"{cle} sur "
                                f"{(self.limites.get(projet) or self.plan_par_defaut).get(cle, 0)}",
                    statut=409)
        for cle, quantite in ressources.items():
            self.consomme.setdefault(projet, {}).setdefault(cle, 0)
            self.consomme[projet][cle] += quantite
        self._suivant += 1
        t = Transaction(reservation=f"res-{self._suivant}", ressources=dict(ressources))
        self._en_cours[t.reservation] = (projet, dict(ressources))
        return t

    async def confirmer(self, t: Transaction, *, id_ressource: str,
                        type_ressource: str, correlation: str = "") -> None:
        self.journal.append(("confirmer", {"reservation": t.reservation,
                                           "id": id_ressource,
                                           "type": type_ressource}))
        garde = self._en_cours.pop(t.reservation, None)
        if garde is not None:
            projet, ressources = garde
            self.tailles[id_ressource] = dict(ressources)
            self.projet_de[id_ressource] = projet
        t.confirmee = True

    async def liberer(self, t: Transaction, *, correlation: str = "") -> None:
        """Rend ce qui avait été retenu. NE LEVE JAMAIS."""
        if t.confirmee:
            return
        garde = self._en_cours.pop(t.reservation, None)
        if garde is None:
            return
        projet, ressources = garde
        for cle, quantite in ressources.items():
            self.consomme.setdefault(projet, {}).setdefault(cle, 0)
            self.consomme[projet][cle] -= quantite
        self.journal.append(("liberer", {"reservation": t.reservation}))

    async def redimensionner(self, *, sujet: str, id_ressource: str,
                             quantites: dict[str, int], correlation: str = "") -> None:
        """Comme le vrai : il compte l ECART, pas la taille entiere."""
        self.journal.append(("redimensionner", {"sujet": sujet, "id": id_ressource,
                                                "quantites": dict(quantites)}))
        anciennes = self.tailles.get(id_ressource, {})
        projet = self.projet_de.get(id_ressource, "")
        for cle, neuve in quantites.items():
            ecart = neuve - anciennes.get(cle, 0)
            if ecart > 0 and self._restant(projet, cle) < ecart:
                raise Refuse(
                    f"quota « {cle} » epuise : agrandissement de {ecart} refuse",
                    motif="quota",
                    explication=f"il reste {max(0, self._restant(projet, cle))} {cle}",
                    statut=409)
        for cle, neuve in quantites.items():
            ecart = neuve - anciennes.get(cle, 0)
            self.consomme.setdefault(projet, {}).setdefault(cle, 0)
            self.consomme[projet][cle] += ecart
        self.tailles[id_ressource] = {**anciennes, **quantites}

    async def rendre(self, *, sujet: str, id_ressource: str,
                     correlation: str = "") -> None:
        self.journal.append(("rendre", {"sujet": sujet, "id": id_ressource}))
        ressources = self.tailles.pop(id_ressource, None)
        projet = self.projet_de.pop(id_ressource, None)
        if ressources is None or projet is None:
            return
        for cle, quantite in ressources.items():
            self.consomme.setdefault(projet, {}).setdefault(cle, 0)
            self.consomme[projet][cle] -= quantite

    # ─── commodités d essai ─────────────────────────────────────────────────

    def etapes(self) -> list[str]:
        return [nom for nom, _ in self.journal]

    def accorder(self, projet: str, **ressources: int) -> None:
        """Accorder un quota, c est activer la ressource. Le remettre a zero, la
        retirer. C est ainsi que « ce projet utilise le stockage, celui-la non »
        s exprime — il n y a pas d interrupteur separe."""
        self.limites.setdefault(projet, {}).update(ressources)
