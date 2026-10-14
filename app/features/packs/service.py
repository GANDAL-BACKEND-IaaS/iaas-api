"""Services des packs. Proprietaire : NAOMI.

La modification d'un pack doit appeler refresh_pending_vm_creates du moteur de demandes (R14).
"""

from app.core.errors import not_implemented


def list_packs(*_args, **_kwargs):
    """F17 : liste le catalogue de packs."""
    raise not_implemented("NAOMI", "liste des packs")


def create_pack(*_args, **_kwargs):
    """F17 : cree un pack. Reserve a un administrateur."""
    raise not_implemented("NAOMI", "creation de pack")


def update_pack(*_args, **_kwargs):
    """F17 : modifie un pack et renvoie les demandes en attente a l'administrateur (R14)."""
    raise not_implemented("NAOMI", "modification de pack")


def delete_pack(*_args, **_kwargs):
    """F17 : supprime un pack seulement s'il ne porte aucune demande de creation en attente (R14)."""
    raise not_implemented("NAOMI", "suppression de pack")
