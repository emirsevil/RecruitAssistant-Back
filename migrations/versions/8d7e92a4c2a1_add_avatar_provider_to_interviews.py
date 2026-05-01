"""Add avatar provider to interviews

Revision ID: 8d7e92a4c2a1
Revises: 2d5d306b5d92
Create Date: 2026-04-30 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d7e92a4c2a1"
down_revision: Union[str, Sequence[str], None] = "2d5d306b5d92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("avatar_provider", sa.String(), nullable=False, server_default="rpm_cartesia"),
    )


def downgrade() -> None:
    op.drop_column("interviews", "avatar_provider")
