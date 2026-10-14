"""Services VM. Proprietaire : NAOMI (port VM).

Le depot reel d'une demande passe aujourd'hui par le moteur partage POST /api/v1/requests.
Ces fonctions sont le point d'entree oriente ressource a completer.
"""

from app.core.errors import not_implemented


def request_create_vm(*_args, **_kwargs):
    """F1 : depose une demande de creation de VM."""
    raise not_implemented("NAOMI", "demande de creation de VM")


def list_vms(*_args, **_kwargs):
    """F3 : liste les VMs visibles dans le projet."""
    raise not_implemented("NAOMI", "liste des VMs")


def get_vm(*_args, **_kwargs):
    """F3 : consulte l'etat d'une VM."""
    raise not_implemented("NAOMI", "consultation d'une VM")


def request_update_vm(*_args, **_kwargs):
    """F2 : depose une demande de modification de VM."""
    raise not_implemented("NAOMI", "demande de modification de VM")


def power_vm(*_args, **_kwargs):
    """F4 : demarre, arrete ou redemarre une VM, sans demande."""
    raise not_implemented("NAOMI", "alimentation d'une VM")


def console_vm(*_args, **_kwargs):
    """F5 : verifie le droit et le partage actif, puis fournit l'acces console."""
    raise not_implemented("NAOMI", "console d'une VM")


def delete_vm(*_args, **_kwargs):
    """F6 : supprime une VM apres confirmation, revoque les partages et appelle le DNS (R24)."""
    raise not_implemented("NAOMI", "suppression d'une VM")


def share_vm(*_args, **_kwargs):
    """F14 : partage une VM avec un autre projet du meme proprietaire."""
    raise not_implemented("NAOMI", "partage d'une VM")
