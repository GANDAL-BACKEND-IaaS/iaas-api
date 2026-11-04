"""Controle d'acces a une action, depuis un projet donne (figure 3).

Ordre de verification :
1. L'utilisateur est membre du projet.
2. Si l'action porte sur une ressource, elle est visible dans le projet.
3. L'utilisateur possede le droit requis (le proprietaire possede tous les droits).
"""

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


async def authorize(
    *,
    iam: IamPort,
    db: Session,
    user_id: str,
    project_id: str,
    required_right: str,
    resource: ResourceView | None = None,
) -> None:
    """Autorise l'action ou leve AppError(forbidden). Ne modifie rien."""
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
