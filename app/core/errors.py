"""Format d'erreur homogene de l'API (exigence non fonctionnelle : API documentee).

Toute reponse d'erreur a la forme :
{"error": {"code": "<code stable>", "message": "<message lisible>", "details": ...}}

Le catalogue ErrorCode est le contrat que les integrateurs peuvent coder en dur.
"""

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    """Codes d'erreur stables, independants du texte du message."""

    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VALIDATION_ERROR = "validation_error"
    BAD_REQUEST = "bad_request"
    INVALID_STATE = "invalid_state"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    NOT_IMPLEMENTED = "not_implemented"
    INTERNAL_ERROR = "internal_error"


# Correspondance code -> statut HTTP. Un code a un seul statut.
STATUS_FOR: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.UPSTREAM_UNAVAILABLE: 503,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.INTERNAL_ERROR: 500,
}

_CODE_FOR_STATUS: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    501: ErrorCode.NOT_IMPLEMENTED,
    503: ErrorCode.UPSTREAM_UNAVAILABLE,
}

logger = logging.getLogger(__name__)

_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNAUTHORIZED: "Authentification requise ou jeton invalide.",
    ErrorCode.FORBIDDEN: "Action refusee.",
    ErrorCode.NOT_FOUND: "Ressource introuvable.",
    ErrorCode.CONFLICT: "Conflit avec l'etat actuel.",
    ErrorCode.VALIDATION_ERROR: "Corps ou parametres invalides.",
    ErrorCode.BAD_REQUEST: "Requete invalide.",
    ErrorCode.INVALID_STATE: "Operation incompatible avec l'etat actuel.",
    ErrorCode.UPSTREAM_UNAVAILABLE: "Un groupe externe est indisponible. Rien n'a ete applique.",
    ErrorCode.NOT_IMPLEMENTED: "Fonctionnalite reservee, pas encore implementee.",
    ErrorCode.INTERNAL_ERROR: "Erreur interne.",
}


class AppError(Exception):
    """Erreur metier renvoyee a l'appelant avec un code stable et un statut HTTP."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code if status_code is not None else STATUS_FOR[code]
        self.details = details
        super().__init__(message)


def error_payload(code: ErrorCode, message: str, details: Any = None) -> dict[str, Any]:
    """Construit le corps JSON d'une erreur. Omet details s'il est absent."""
    error: dict[str, Any] = {"code": code.value, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def not_implemented(owner: str, subject: str) -> AppError:
    """Signale une route dont l'implementation est reservee a un developpeur."""
    return AppError(
        ErrorCode.NOT_IMPLEMENTED,
        f"Implementation reservee a {owner} : {subject}.",
    )


def upstream_unavailable(group: str) -> AppError:
    """Refuse une action qui depend d'un groupe externe indisponible (jamais a moitie)."""
    return AppError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        f"Le groupe {group} est indisponible. Aucune modification n'a ete appliquee.",
    )


def error_responses(*codes: ErrorCode) -> dict[int, dict[str, Any]]:
    """Decrit les erreurs d'une route pour OpenAPI. A passer dans `responses=`."""
    documented: dict[int, dict[str, Any]] = {}
    for code in codes:
        status = STATUS_FOR[code]
        slot = documented.setdefault(
            status,
            {
                "description": "Erreur : voir les exemples pour les codes possibles.",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["error"],
                            "properties": {
                                "error": {
                                    "type": "object",
                                    "required": ["code", "message"],
                                    "properties": {
                                        "code": {"type": "string"},
                                        "message": {"type": "string"},
                                        "details": {},
                                    },
                                }
                            },
                        },
                        "examples": {},
                    }
                },
            },
        )
        slot["content"]["application/json"]["examples"][code.value] = {
            "summary": code.value,
            "value": error_payload(code, _MESSAGES[code]),
        }
    return documented


def register_exception_handlers(app: FastAPI) -> None:
    """Branche les handlers qui garantissent le format d'erreur unique."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = _CODE_FOR_STATUS.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else _MESSAGES[code]
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, message),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR,
                _MESSAGES[ErrorCode.VALIDATION_ERROR],
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Le message reste generique : aucune donnee sensible dans la reponse.
        logger.exception("Erreur interne non geree")
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.INTERNAL_ERROR, _MESSAGES[ErrorCode.INTERNAL_ERROR]),
        )
