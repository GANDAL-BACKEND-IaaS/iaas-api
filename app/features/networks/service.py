"""Services reseau. Proprietaire : KOM (port Reseau)."""

from app.core.errors import not_implemented


def create_network(*_args, **_kwargs):
    """F7 : cree un reseau dans un projet. Action directe, sans demande."""
    raise not_implemented("KOM", "creation de reseau")


def list_networks(*_args, **_kwargs):
    """F7 : liste les reseaux du projet."""
    raise not_implemented("KOM", "liste des reseaux")


def attach_vm(*_args, **_kwargs):
    """F7 : rattache une VM visible dans le projet a un reseau."""
    raise not_implemented("KOM", "rattachement d'une VM")


def detach_vm(*_args, **_kwargs):
    """F7 : retire une VM d'un reseau."""
    raise not_implemented("KOM", "retrait d'une VM")


def delete_network(*_args, **_kwargs):
    """F7 : supprime un reseau du projet."""
    raise not_implemented("KOM", "suppression de reseau")
