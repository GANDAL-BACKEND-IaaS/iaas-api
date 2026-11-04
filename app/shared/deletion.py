"""Protocole commun de suppression en deux temps (section 1.5).

Phase 1 : corps `{}` (ou sans `confirmation_text`) -> apercu, aucun effet.
Phase 2 : `confirmation_text` doit valoir exactement `SUPPRIMER <nom>`.
Un texte incorrect est un 400 ; une dependance externe en panne est un 503 et
aucun element local n'est marque supprime.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError, ErrorCode


class DeletionIn(BaseModel):
    """Corps des routes de suppression. Omis en phase 1, renseigne en phase 2."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"confirmation_text": "SUPPRIMER alpha"}]})

    confirmation_text: str | None = Field(default=None, max_length=255)


class DeletionPreviewOut(BaseModel):
    """Reponse de la phase 1 : texte exact a renvoyer et avertissement lisible."""

    confirmation_required: Literal[True] = True
    confirmation_text: str
    warning: str


class DeletionOut(BaseModel):
    """Reponse de la phase 2 : suppression effectivement appliquee."""

    deleted: Literal[True] = True
    resource_type: str
    resource_id: str
    message: str


DeletionResponse = DeletionPreviewOut | DeletionOut


def expected_text(name: str) -> str:
    """Texte exact attendu en phase 2."""
    return f"SUPPRIMER {name}"


def is_confirmed(confirmation_text: str | None, expected: str) -> bool:
    """Retourne False pour un apercu, True pour une confirmation exacte, sinon 400."""
    if confirmation_text is None:
        return False
    if confirmation_text != expected:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            "Le texte de confirmation ne correspond pas au texte attendu.",
            details={"expected": expected},
        )
    return True
