"""Pagination des listes (exigence non fonctionnelle : echelle et performance).

Toutes les listes de l'API renvoient une Page : items, total, page, page_size.
"""

from collections.abc import Sequence
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams(BaseModel):
    """Parametres de pagination communs a toutes les listes."""

    page: int = Field(default=1, ge=1, description="Numero de page, a partir de 1.")
    page_size: int = Field(default=20, ge=1, le=100, description="Taille de page, 100 maximum.")


class Page(BaseModel, Generic[T]):
    """Page de resultats. Le type T est le schema sortant de chaque element."""

    items: list[T]
    total: int = Field(description="Nombre total d'elements, toutes pages confondues.")
    page: int
    page_size: int


def get_page_params(
    page: int = Query(1, ge=1, description="Numero de page, a partir de 1."),
    page_size: int = Query(20, ge=1, le=100, description="Taille de page, 100 maximum."),
) -> PageParams:
    """Dependance FastAPI : lit la pagination dans la query string."""
    return PageParams(page=page, page_size=page_size)


def paginate(db: Session, statement: Select, params: PageParams) -> tuple[Sequence, int]:
    """Applique LIMIT/OFFSET et renvoie (elements, total). Ne commit pas."""
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = int(db.scalar(count_statement) or 0)
    offset = (params.page - 1) * params.page_size
    rows = db.scalars(statement.offset(offset).limit(params.page_size)).all()
    return rows, total
