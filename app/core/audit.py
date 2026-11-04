"""Journal d'audit horodate (exigence non fonctionnelle : tracabilite).

Chaque evenement metier important laisse une ligne : auteur, action, cible, date.
Aucune donnee sensible (mot de passe, jeton, secret) n'est acceptee dans `data`.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.shared.models.audit import AuditLog

_FORBIDDEN_KEYS = frozenset({"password", "token", "secret", "authorization", "access_token"})


def record_audit(
    db: Session,
    *,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    data: dict[str, Any] | None = None,
) -> AuditLog:
    """Ajoute une ligne au journal. L'appelant est responsable du commit."""
    payload = dict(data or {})
    leaked = sorted(key for key in payload if key.lower() in _FORBIDDEN_KEYS)
    if leaked:
        raise ValueError(f"Donnee sensible refusee dans le journal : {', '.join(leaked)}.")
    row = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=payload,
    )
    db.add(row)
    return row
