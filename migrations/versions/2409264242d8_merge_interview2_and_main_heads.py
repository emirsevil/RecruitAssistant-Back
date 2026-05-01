"""merge interview2 and main heads

Revision ID: 2409264242d8
Revises: 2f88837e306c, 8d7e92a4c2a1
Create Date: 2026-05-01 11:49:39.801564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2409264242d8'
down_revision: Union[str, Sequence[str], None] = ('2f88837e306c', '8d7e92a4c2a1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
