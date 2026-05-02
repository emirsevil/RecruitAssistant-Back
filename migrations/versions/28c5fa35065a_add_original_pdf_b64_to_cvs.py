"""add original_pdf_b64 to cvs

Revision ID: 28c5fa35065a
Revises: 5612dbc43bfe
Create Date: 2026-05-02 18:42:00.359618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28c5fa35065a'
down_revision: Union[str, Sequence[str], None] = '5612dbc43bfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("cvs")}
    if "original_pdf_b64" not in existing:
        op.add_column("cvs", sa.Column("original_pdf_b64", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("cvs")}
    if "original_pdf_b64" in existing:
        op.drop_column("cvs", "original_pdf_b64")
