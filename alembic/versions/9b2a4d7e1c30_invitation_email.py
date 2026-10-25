"""Ajoute l'email du destinataire aux invitations.

L'identifiant IAM reste la cle canonique. L'email est conserve comme instantane
pour l'affichage et l'audit, y compris si le compte change d'adresse plus tard.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b2a4d7e1c30"
down_revision: Union[str, Sequence[str], None] = "49c95feb0fac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute la colonne nullable pour les invitations deja existantes."""
    op.add_column(
        "invitations",
        sa.Column("invitee_email", sa.String(length=320), nullable=True),
    )


def downgrade() -> None:
    """Retire l'email instantane des invitations."""
    op.drop_column("invitations", "invitee_email")
