"""Format d'erreur homogene de l'API.

Toute reponse d'erreur a la forme :

    {"error": {"code": "<code stable>", "message": "<message lisible>", "details": null}}

Le catalogue ErrorCode est le contrat que les integrateurs peuvent coder en dur.
Les erreurs de routage (404, 405) et de validation (422) passent par le meme
enveloppe : aucun `{"detail": ...}` FastAPI ne doit fuiter.
"""

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


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
    ErrorCode.INTERNAL_ERROR: 500,
}

_CODE_FOR_STATUS: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    500: ErrorCode.INTERNAL_ERROR,
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
    """Construit le corps JSON d'une erreur. `details` est toujours present."""
    return {"error": {"code": code.value, "message": message, "details": details}}


def upstream_unavailable(group: str) -> AppError:
    """Refuse une action qui depend d'un groupe externe indisponible (jamais a moitie)."""
    return AppError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        f"Le groupe {group} est indisponible. Aucune modification n'a ete appliquee.",
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Normalise les erreurs Pydantic en une liste lisible {field, message, ...}."""
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
        item: dict[str, Any] = {
            "field": ".".join(location) or "body",
            "message": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        context = error.get("ctx") or {}
        if "ge" in context:
            item["minimum"] = context["ge"]
        if "gt" in context:
            item["minimum_exclusive"] = context["gt"]
        if "le" in context:
            item["maximum"] = context["le"]
        if "lt" in context:
            item["maximum_exclusive"] = context["lt"]
        if "min_length" in context:
            item["min_length"] = context["min_length"]
        if "max_length" in context:
            item["max_length"] = context["max_length"]
        details.append(item)
    return details


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
                                    "required": ["code", "message", "details"],
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

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODE_FOR_STATUS.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        if exc.status_code in (404, 405):
            message = (
                "Ressource introuvable."
                if exc.status_code == 404
                else "Methode non autorisee pour cette ressource."
            )
        else:
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
                details=_validation_details(exc),
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
