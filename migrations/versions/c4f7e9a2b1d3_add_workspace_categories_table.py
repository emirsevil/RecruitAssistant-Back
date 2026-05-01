"""add workspace categories table

Revision ID: c4f7e9a2b1d3
Revises: 2409264242d8
Create Date: 2026-05-01 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f7e9a2b1d3"
down_revision: Union[str, Sequence[str], None] = "2409264242d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("workspace_categories"):
        return

    op.create_table(
        "workspace_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspace_categories_id"), "workspace_categories", ["id"], unique=False)
    op.create_index(
        op.f("ix_workspace_categories_workspace_id"),
        "workspace_categories",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    if not _table_exists("workspace_categories"):
        return

    op.drop_index(op.f("ix_workspace_categories_workspace_id"), table_name="workspace_categories")
    op.drop_index(op.f("ix_workspace_categories_id"), table_name="workspace_categories")
    op.drop_table("workspace_categories")
