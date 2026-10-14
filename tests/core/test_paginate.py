"""Cas nominaux et limites de la pagination."""

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.pagination import PageParams, get_page_params, paginate
from app.shared.models.projects import Project
from tests.support import add_project


def test_paginate_returns_slice_and_total(db):
    """La page 2 contient les elements attendus et le total complet."""
    for index in range(5):
        add_project(db, "u", f"p{index}", f"n{index}")
    statement = select(Project).order_by(Project.name)
    rows, total = paginate(db, statement, PageParams(page=2, page_size=2))
    assert total == 5
    assert [row.name for row in rows] == ["n2", "n3"]


def test_paginate_past_the_end_is_empty(db):
    """Une page au-dela des resultats est vide, le total reste exact."""
    add_project(db, "u", "p1", "n1")
    rows, total = paginate(db, select(Project).order_by(Project.name), PageParams(page=9, page_size=20))
    assert list(rows) == []
    assert total == 1


def test_page_params_reject_zero():
    """page et page_size commencent a 1 et sont plafonnes."""
    with pytest.raises(ValidationError):
        PageParams(page=0, page_size=20)
    with pytest.raises(ValidationError):
        PageParams(page=1, page_size=101)
    assert get_page_params(3, 10) == PageParams(page=3, page_size=10)
