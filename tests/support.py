"""Helpers partages par les tests. Ce module n'est pas collecte comme une suite."""

from app.shared.models.projects import Project
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


def add_project(db, owner_id: str, project_id: str = "p1", name: str = "Alpha") -> Project:
    """Insere un projet metier. N'appelle pas l'IAM."""
    project = Project(id=project_id, name=name, owner_id=owner_id)
    db.add(project)
    db.commit()
    return project


def add_vm(db, project_id: str, vm_id: str = "vm-1", **kwargs) -> Vm:
    """Insere une VM dans son projet d'origine."""
    vm = Vm(
        id=vm_id,
        origin_project_id=project_id,
        name=kwargs.get("name", "web"),
        ram=kwargs.get("ram", 2048),
        cpu=kwargs.get("cpu", 2),
        vram=kwargs.get("vram", 128),
        ssd=kwargs.get("ssd", 40),
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
        size=kwargs.get("size", 100),
        state=kwargs.get("state", "available"),
    )
    db.add(storage)
    db.commit()
    return storage


async def own_project(db, iam, project_id: str = "p1", email: str = "u@x.cm") -> str:
    """Cree le projet des deux cotes : IAM (droits) et base (metier)."""
    uid = await user_id(iam, email)
    await iam.create_project(uid, project_id)
    add_project(db, uid, project_id)
    return uid
