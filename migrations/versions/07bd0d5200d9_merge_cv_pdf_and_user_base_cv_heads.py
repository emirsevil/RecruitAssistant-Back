"""merge cv pdf and user base_cv heads

Revision ID: 07bd0d5200d9
Revises: 28c5fa35065a, db4f96fe3be4
Create Date: 2026-05-02 23:13:03.905808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07bd0d5200d9'
down_revision: Union[str, Sequence[str], None] = ('28c5fa35065a', 'db4f96fe3be4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
