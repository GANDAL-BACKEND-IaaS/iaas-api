"""Retire les espaces de stockage du perimetre de l'API."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "6c4d2a8e1f70"
down_revision: Union[str, Sequence[str], None] = "9b2a4d7e1c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Supprime les donnees de stockage et les references de droits associees."""
    connection = op.get_bind()

    for table_name in ("memberships", "invitations"):
        table = sa.table(
            table_name,
            sa.column("id", sa.String()),
            sa.column("additional_rights", sa.JSON()),
        )
        rows = connection.execute(sa.select(table.c.id, table.c.additional_rights))
        for row_id, rights in rows:
            retained = [right for right in (rights or []) if not right.startswith("storage.")]
            if retained != rights:
                connection.execute(
                    table.update()
                    .where(table.c.id == row_id)
                    .values(additional_rights=retained)
                )

    op.execute("DELETE FROM profile_rights WHERE right_code LIKE 'storage.%'")
    op.execute("DELETE FROM rights WHERE code LIKE 'storage.%'")
    op.execute("DELETE FROM resource_shares WHERE resource_type = 'storage'")
    op.execute(
        "DELETE FROM resource_requests WHERE kind IN ('storage_create', 'storage_update')"
    )
    op.drop_index("ix_storages_ip_address", table_name="storages")
    op.drop_index("ix_storages_origin_project_id", table_name="storages")
    op.drop_table("storages")


def downgrade() -> None:
    """Recree la table vide ; les anciennes donnees ne peuvent pas etre restaurees."""
    op.create_table(
        "storages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("origin_project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("size_gb", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["origin_project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storages_ip_address", "storages", ["ip_address"], unique=False)
    op.create_index(
        "ix_storages_origin_project_id",
        "storages",
        ["origin_project_id"],
        unique=False,
    )
