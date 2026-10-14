"""Services stockage. Proprietaire : TABA (port Espaces)."""

from app.core.errors import not_implemented


def request_create_storage(*_args, **_kwargs):
    """F8 : depose une demande de creation de stockage."""
    raise not_implemented("TABA", "demande de creation de stockage")


def list_storages(*_args, **_kwargs):
    """F10 : liste les stockages visibles dans le projet."""
    raise not_implemented("TABA", "liste des stockages")


def get_storage(*_args, **_kwargs):
    """F10 : consulte un stockage."""
    raise not_implemented("TABA", "consultation d'un stockage")


def request_update_storage(*_args, **_kwargs):
    """F9 : depose une demande de modification de taille."""
    raise not_implemented("TABA", "demande de modification de stockage")


def delete_storage(*_args, **_kwargs):
    """F11 : supprime un stockage apres confirmation, meme s'il contient des donnees."""
    raise not_implemented("TABA", "suppression d'un stockage")


def share_storage(*_args, **_kwargs):
    """F14 : partage un stockage avec un autre projet du meme proprietaire."""
    raise not_implemented("TABA", "partage d'un stockage")
