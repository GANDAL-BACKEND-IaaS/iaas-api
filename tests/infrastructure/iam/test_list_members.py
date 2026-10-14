"""Cas nominaux et limites de list_members sur le mock IAM."""

import pytest

from app.application.ports.iam import ProjectNotFound


async def test_list_members_includes_owner_and_guest(iam):
    """Le proprietaire a tous les droits connus. L'invite n'a que ceux accordes."""
    owner = iam.add_user("alice@x.cm", "pw")
    guest = iam.add_user("bob@x.cm", "pw")
    await iam.create_project(owner.user_id, "p1")
    await iam.invite_user(guest.user_id, "p1", ["vm.view"])
    members = {item.user_id: item for item in await iam.list_members("p1")}
    assert members[owner.user_id].is_owner is True
    assert "vm.view" in members[owner.user_id].rights
    assert members[guest.user_id].is_owner is False
    assert members[guest.user_id].rights == frozenset({"vm.view"})


async def test_list_members_unknown_project(iam):
    """Un projet absent leve ProjectNotFound."""
    with pytest.raises(ProjectNotFound):
        await iam.list_members("absent")
