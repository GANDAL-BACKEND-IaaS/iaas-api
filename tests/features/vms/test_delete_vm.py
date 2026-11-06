"""Cas nominaux et limites de la suppression d'une VM (F6)."""

import pytest

from app.core.dependencies import get_decision
from app.infrastructure.iam.fake_decision import FakeDecisionClient
from app.main import app
from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare
from app.shared.models.vms import Vm
from tests.support import add_project, add_vm, login_header, own_project, user_id

PLAN = {"vm_count": 5, "vcpu": 16, "ram_gb": 32, "disk_gb": 500}


@pytest.fixture
def decision():
    fake = FakeDecisionClient(plan_par_defaut=PLAN)
    app.dependency_overrides[get_decision] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_decision, None)


def _confirm(client, path, headers):
    preview = client.post(path, headers=headers, json={})
    assert preview.status_code == 200, preview.text
    return client.post(
        path, headers=headers, json={"confirmation_text": preview.json()["confirmation_text"]}
    )


async def test_delete_vm_revokes_share_and_deletes_vm(client, db, iam):
    """La suppression revoque le partage et supprime la VM via l'hyperviseur."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by=uid,
            status=ShareStatus.ACTIVE.value,
        )
    )
    db.commit()
    headers = await login_header(iam)
    response = _confirm(client, "/api/v1/projects/p1/vms/vm-1/deletion", headers)
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert db.get(Vm, "vm-1") is None
    share = db.query(ResourceShare).one()
    assert share.status == ShareStatus.REVOKED.value


async def test_delete_vm_hypervisor_down_keeps_vm(client, db, iam, hypervisor):
    """Si l'hyperviseur est indisponible, la VM reste en base."""
    await own_project(db, iam)
    add_vm(db, "p1")
    headers = await login_header(iam)
    preview = client.post(
        "/api/v1/projects/p1/vms/vm-1/deletion", headers=headers, json={}
    ).json()
    hypervisor.available = False
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/deletion",
        headers=headers,
        json={"confirmation_text": preview["confirmation_text"]},
    )
    assert response.status_code == 503
    assert db.get(Vm, "vm-1") is not None


async def test_delete_vm_restitutes_quota(client, db, iam, decision):
    await own_project(db, iam)
    headers = await login_header(iam)
    created = client.post(
        "/api/v1/projects/p1/vms/direct",
        headers=headers,
        json={
            "name": "quota-vm",
            "configuration": {"ram_gb": 2, "vcpu": 2, "vram_gb": 0, "ssd_gb": 20},
        },
    )
    assert created.status_code == 201, created.text
    vm_id = created.json()["target_resource_id"]

    response = _confirm(
        client, f"/api/v1/projects/p1/vms/{vm_id}/deletion", headers
    )

    assert response.status_code == 200, response.text
    assert decision.consomme["p1"]["vm_count"] == 0
    assert decision.consomme["p1"]["vcpu"] == 0
    assert decision.consomme["p1"]["ram_gb"] == 0
    assert decision.consomme["p1"]["disk_gb"] == 0
    assert decision.etapes().count("rendre") == 1


def test_delete_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/vms/vm-1/deletion", json={})
    assert response.status_code == 401
