"""Helpers partages par les tests. Ce module n'est pas collecte comme une suite."""

from app.shared.models.packs import Pack
from app.shared.models.projects import Membership, Project
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm


async def user_id(iam, email: str = "u@x.cm", password: str = "pw") -> str:
    """Retourne l'identifiant IAM d'un compte deja cree dans le mock."""
    token = await iam.login(email, password)
    identity = await iam.validate_token(token.access_token)
    return identity.user_id


def bearer(token: str) -> dict[str, str]:
    """Construit l'en-tete Authorization."""
    return {"Authorization": f"Bearer {token}"}


async def login_header(iam, email: str = "u@x.cm") -> dict[str, str]:
    """En-tete Bearer pour un utilisateur du mock IAM."""
    token = await iam.login(email, "pw")
    return bearer(token.access_token)


def add_project(
    db, owner_id: str, project_id: str = "p1", name: str | None = None
) -> Project:
    """Insere un projet metier et l'appartenance proprietaire. N'appelle pas l'IAM."""
    project = Project(
        id=project_id, name=name or f"Projet {project_id}", owner_id=owner_id
    )
    db.add(project)
    db.add(
        Membership(
            project_id=project_id,
            user_id=owner_id,
            role="owner",
            additional_rights=[],
        )
    )
    db.commit()
    return project


def add_vm(db, project_id: str, vm_id: str = "vm-1", **kwargs) -> Vm:
    """Insere une VM dans son projet d'origine."""
    vm = Vm(
        id=vm_id,
        origin_project_id=project_id,
        name=kwargs.get("name", "web"),
        ip_address=kwargs.get("ip_address"),
        ram_gb=kwargs.get("ram_gb", 8),
        vcpu=kwargs.get("vcpu", 2),
        vram_gb=kwargs.get("vram_gb", 0),
        ssd_gb=kwargs.get("ssd_gb", 40),
        state=kwargs.get("state", "stopped"),
        pack_id=kwargs.get("pack_id"),
    )
    db.add(vm)
    db.commit()
    return vm


def add_storage(db, project_id: str, storage_id: str = "st-1", **kwargs) -> Storage:
    """Insere un espace de stockage dans son projet d'origine."""
    storage = Storage(
        id=storage_id,
        origin_project_id=project_id,
        name=kwargs.get("name", "docs"),
        ip_address=kwargs.get("ip_address"),
        size_gb=kwargs.get("size_gb", 100),
        state=kwargs.get("state", "available"),
    )
    db.add(storage)
    db.commit()
    return storage


def add_pack(db, name: str = "Standard", **kwargs) -> Pack:
    """Insere un pack en unites explicites (Go et vCPU)."""
    pack = Pack(
        name=name,
        description=kwargs.get("description", ""),
        ram_gb=kwargs.get("ram_gb", 8),
        vcpu=kwargs.get("vcpu", 4),
        vram_gb=kwargs.get("vram_gb", 0),
        ssd_gb=kwargs.get("ssd_gb", 80),
    )
    db.add(pack)
    db.commit()
    return pack


async def own_project(db, iam, project_id: str = "p1", email: str = "u@x.cm") -> str:
    """Cree le projet des deux cotes : IAM (droits) et base (metier)."""
    uid = await user_id(iam, email)
    await iam.create_project(uid, project_id)
    add_project(db, uid, project_id)
    return uid
