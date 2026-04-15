"""merge main and analysis branches

Revision ID: 7e71270fdf52
Revises: 0004, a1b2c3d4e5f6
Create Date: 2026-04-14 11:56:40.524183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e71270fdf52'
down_revision: Union[str, Sequence[str], None] = ('0004', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
