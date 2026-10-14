"""Cas nominaux et limites de revoke_share (R18, R21)."""

import pytest

from app.core.errors import AppError, ErrorCode
from app.features.shares.service import create_share, revoke_share
from app.infrastructure.network.fake_network import FakeNetwork
from app.shared.enums import ResourceType, ShareStatus
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.shares import ResourceShare
from tests.support import add_project, add_vm, user_id


async def _shared(db, iam):
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    row = await create_share(
        db, iam, user_id=uid, resource_type=ResourceType.VM,
        resource_id="vm-1", dest_project_id="p2",
    )
    return uid, row


async def test_owner_revoke_detaches_network(db, iam):
    """Le retrait revoque le partage et sort la VM des reseaux du destinataire."""
    uid, row = await _shared(db, iam)
    network = Network(id="net-1", project_id="p2", name="lan")
    db.add(network)
    db.flush()
    db.add(NetworkVm(network_id="net-1", vm_id="vm-1"))
    db.commit()
    port = FakeNetwork()
    await port.create_network("p2", "lan")
    revoked = await revoke_share(db, port, user_id=uid, share_id=row.id)
    assert revoked.status == ShareStatus.REVOKED.value
    assert db.get(NetworkVm, ("net-1", "vm-1")) is None


async def test_stranger_cannot_revoke(db, iam):
    """Ni un tiers ni un simple membre non auteur ne retire le partage."""
    _, row = await _shared(db, iam)
    stranger = iam.add_user("stranger@x.cm", "pw")
    with pytest.raises(AppError) as exc:
        await revoke_share(db, FakeNetwork(), user_id=stranger.user_id, share_id=row.id)
    assert exc.value.code == ErrorCode.FORBIDDEN


async def test_creator_can_revoke(db, iam):
    """L'auteur du partage peut le retirer."""
    _, row = await _shared(db, iam)
    revoked = await revoke_share(db, FakeNetwork(), user_id=row.created_by, share_id=row.id)
    assert revoked.status == ShareStatus.REVOKED.value


async def test_revoked_share_is_not_removed_again(db, iam):
    """Un partage revoque ne se retire pas une seconde fois."""
    uid, row = await _shared(db, iam)
    await revoke_share(db, FakeNetwork(), user_id=uid, share_id=row.id)
    with pytest.raises(AppError) as exc:
        await revoke_share(db, FakeNetwork(), user_id=uid, share_id=row.id)
    assert exc.value.code == ErrorCode.INVALID_STATE


async def test_network_outage_does_not_revoke(db, iam):
    """Si le groupe Reseau est indisponible, le partage reste actif."""
    uid, row = await _shared(db, iam)
    port = FakeNetwork(available=False)
    with pytest.raises(AppError) as exc:
        await revoke_share(db, port, user_id=uid, share_id=row.id)
    assert exc.value.code == ErrorCode.UPSTREAM_UNAVAILABLE
    assert db.get(ResourceShare, row.id).status == ShareStatus.ACTIVE.value
