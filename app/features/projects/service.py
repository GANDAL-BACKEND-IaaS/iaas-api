"""Services projets, membres et invitations. Proprietaire : ZUCHUON (port IAM).

Les fonctions levent not_implemented tant que la logique metier n'est pas branchee.
Le controle d'acces, les modeles et le moteur de demandes sont deja disponibles.
"""

from app.core.errors import not_implemented


def create_project(*_args, **_kwargs):
    """F12 : cree un projet dont l'appelant devient proprietaire."""
    raise not_implemented("ZUCHUON", "creation de projet")


def list_projects(*_args, **_kwargs):
    """F12 : liste les projets de l'appelant."""
    raise not_implemented("ZUCHUON", "liste des projets")


def get_project(*_args, **_kwargs):
    """F12 : consulte un projet."""
    raise not_implemented("ZUCHUON", "consultation de projet")


def rename_project(*_args, **_kwargs):
    """F12 : renomme un projet. Reserve au proprietaire."""
    raise not_implemented("ZUCHUON", "renommage de projet")


def delete_project(*_args, **_kwargs):
    """F12 : supprime un projet en cascade apres confirmation (R23)."""
    raise not_implemented("ZUCHUON", "suppression de projet")


def list_members(*_args, **_kwargs):
    """F12 : liste les membres d'un projet."""
    raise not_implemented("ZUCHUON", "liste des membres")


def create_invitation(*_args, **_kwargs):
    """F13 : invite un utilisateur avec des droits plafonnes (R8)."""
    raise not_implemented("ZUCHUON", "creation d'invitation")


def list_invitations(*_args, **_kwargs):
    """F13 : liste les invitations d'un projet."""
    raise not_implemented("ZUCHUON", "liste des invitations")


def accept_invitation(*_args, **_kwargs):
    """F13 : l'invite accepte l'invitation."""
    raise not_implemented("ZUCHUON", "acceptation d'invitation")


def refuse_invitation(*_args, **_kwargs):
    """F13 : l'invite refuse l'invitation."""
    raise not_implemented("ZUCHUON", "refus d'invitation")


def cancel_invitation(*_args, **_kwargs):
    """F13 : l'auteur ou le proprietaire annule une invitation non acceptee (R9)."""
    raise not_implemented("ZUCHUON", "annulation d'invitation")
