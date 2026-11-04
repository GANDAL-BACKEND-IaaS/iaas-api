"""Controle d'acces a une action, depuis un projet donne (figure 3).

Ordre de verification :
1. L'utilisateur est membre du projet.
2. Si l'action porte sur une ressource, elle est visible dans le projet.
3. L'utilisateur possede le droit requis (le proprietaire possede tous les droits).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.ports.decision import DecisionPort

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort
from app.core.errors import AppError, ErrorCode
from app.shared.policies.visibility import is_resource_visible


@dataclass(frozen=True)
class ResourceView:
    """Ressource visee par une action, vue depuis son projet d'origine."""

    resource_type: str
    resource_id: str
    origin_project_id: str


# ─── DU DROIT A L ACTION IAM ─────────────────────────────────────────────────
#
# Chaque appel a `authorize` nomme deja un DROIT. L action IAM s en deduit, donc
# AUCUN appelant n a besoin de changer : la greffe se fait en un seul endroit.
#
# Pourquoi cette table plutot qu un parametre de plus a treize endroits : ce
# depot est en developpement actif, et quarante changements de signature
# entreraient en conflit avec ce qui s y ecrit en ce moment. Un droit absent de
# la table ne demande rien a IAM — le defaut est donc l ancien comportement, pas
# un refus surprise.
#
# « vm.power » vaut « vm:stop » : un redemarrage est un arret suivi d un
# demarrage, et on exige la plus forte des deux. La table ne distingue pas
# start/stop parce que le droit ne le distingue pas non plus.
_ACTION_POUR_DROIT: dict[str, str] = {
    "vm.request_create": "vm:create",
    "vm.request_update": "vm:update",
    "vm.view":           "vm:read",
    "vm.power":          "vm:stop",
    "vm.delete":         "vm:delete",
    "vm.console":        "vm:console",
    "vm.share":          "vm:grant",
    "vm.network":        "vm:update",
    "project.invite":    "projet:membre:invite",
}


def _resolveur_par_defaut():
    return None


# COMMENT LE PORT ARRIVE ICI, et pourquoi ce n est pas de l injection.
# `main.py` appelle `brancher_decision(get_decision)` au demarrage ; les tests le
# remplacent par ce qu ils veulent. C est un localisateur de service, donc moins
# propre qu un parametre — et je le dis plutot que de le cacher. Le raisonnement :
# faire passer le port par les signatures demanderait de toucher quatre services
# et quatre routeurs dans un depot ou l equipe ecrit en ce moment. Le faire
# proprement par injection est le bon etat final, et il appartient a qui tient ce
# code.
_resolveur = _resolveur_par_defaut


def brancher_decision(resolveur) -> None:
    """Branche (ou debranche, avec `None`) le service de decision."""
    global _resolveur
    _resolveur = resolveur or _resolveur_par_defaut


async def authorize(
    *,
    iam: IamPort,
    db: Session,
    user_id: str,
    project_id: str,
    required_right: str,
    resource: ResourceView | None = None,
    decision: "DecisionPort | None" = None,
    action: str | None = None,
    contexte: dict | None = None,
) -> None:
    """Autorise l'action ou leve AppError(forbidden). Ne modifie rien.

    DEUX QUESTIONS, ET ELLES NE SONT PAS LA MEME. Les droits (`required_right`)
    disent ce que l'utilisateur porte dans ce projet ; c'est stable d'une requete
    a l'autre. La DECISION d'IAM (`action`) dit s'il a le droit de faire CECI,
    MAINTENANT — ce qui depend de son role a cet instant, du second facteur, de
    l'etat du projet et des politiques en vigueur.

    Les deux sont demandees ici, dans cet ordre : les droits d'abord, parce qu'ils
    ne coutent rien et qu'un non-membre n'a pas a faire travailler IAM.

    `decision=None` laisse le comportement d'avant, a l'identique. Les appels qui
    ne passent pas `action` ne demandent rien a IAM, et c'est ainsi que la greffe
    reste additive.
    """
    projects = await iam.list_projects(user_id)
    if project_id not in projects:
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")
    if resource is not None and not is_resource_visible(
        db,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        origin_project_id=resource.origin_project_id,
        project_id=project_id,
    ):
        raise AppError(ErrorCode.FORBIDDEN, "La ressource n'est pas visible dans ce projet.")
    rights = await iam.get_rights(user_id, project_id)
    if required_right not in rights:
        raise AppError(ErrorCode.FORBIDDEN, f"Droit requis manquant : {required_right}.")
    if decision is None:
        decision = _resolveur()
    if action is None:
        action = _ACTION_POUR_DROIT.get(required_right)
    if decision is not None and action is not None:
        # LA DECISION PORTE SUR LA PERSONNE, jamais sur le backend : c'est tout
        # l'objet de la delegation. Un refus leve `Refuse`, que le gestionnaire
        # de `main.py` traduit en problem+json avec le motif d'IAM — « il vous
        # reste 0 vCPU sur 4 » plutot que « erreur interne ».
        ressource = {"type": "projet", "id": project_id, "projet": project_id}
        if resource is not None:
            ressource = {"type": str(resource.resource_type),
                         "id": str(resource.resource_id), "projet": project_id}
        await decision.autoriser(sujet=user_id, action=action,
                                 ressource=ressource, contexte=contexte)


def resolveur():
    """Le service de decision branche, ou None. Expose pour les appelants qui en
    ont besoin HORS de `authorize` — l acceptation d une demande, qui retient du
    quota et ne fait pas que decider."""
    return _resolveur()
