"""Cas nominaux et limites de list_requests."""

from app.application.ports.iam import GlobalRole
from app.core.pagination import PageParams
from app.features.requests.service import list_requests, submit_request
from app.shared.enums import RequestKind, RequestStatus
from tests.support import add_project, own_project, user_id

_CUSTOM = {"name": "web", "ram": 2048, "cpu": 2, "vram": 128, "ssd": 40}


async def test_user_sees_only_own_requests(db, iam):
    """Un utilisateur ne liste que les demandes dont il est l'auteur."""
    uid = await own_project(db, iam)
    await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    other = iam.add_user("other@x.cm", "pw")
    await iam.create_project(other.user_id, "p9")
    add_project(db, other.user_id, "p9", "Autre")
    await submit_request(
        db, iam, author_id=other.user_id, project_id="p9", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    rows, total = list_requests(
        db, actor_id=uid, actor_role=GlobalRole.USER, params=PageParams(page=1, page_size=20),
    )
    assert total == 1
    assert rows[0].author_id == uid


async def test_admin_can_filter_by_status(db, iam):
    """L'administrateur voit tout et peut filtrer par statut."""
    uid = await own_project(db, iam)
    await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    admin = await user_id(iam, "root@x.cm")
    _, pending = list_requests(
        db, actor_id=admin, actor_role=GlobalRole.ADMIN, params=PageParams(),
        status=RequestStatus.PENDING,
    )
    _, accepted = list_requests(
        db, actor_id=admin, actor_role=GlobalRole.ADMIN, params=PageParams(),
        status=RequestStatus.ACCEPTED,
    )
    assert pending == 1
    assert accepted == 0


async def test_page_past_the_end_is_empty(db, iam):
    """Une page trop loin est vide sans perdre le total."""
    uid = await own_project(db, iam)
    await submit_request(
        db, iam, author_id=uid, project_id="p1", kind=RequestKind.VM_CREATE,
        payload=_CUSTOM, target_resource_id=None,
    )
    rows, total = list_requests(
        db, actor_id=uid, actor_role=GlobalRole.USER, params=PageParams(page=3, page_size=20),
    )
    assert rows == []
    assert total == 1
