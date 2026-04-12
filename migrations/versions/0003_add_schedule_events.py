"""add schedule events

Revision ID: 0003
Revises: 2d5d306b5d92
Create Date: 2026-04-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "2d5d306b5d92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_schedule_events_id"), "schedule_events", ["id"], unique=False)
    op.create_index(op.f("ix_schedule_events_user_id"), "schedule_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_schedule_events_start_time"), "schedule_events", ["start_time"], unique=False)
    op.create_index(op.f("ix_schedule_events_end_time"), "schedule_events", ["end_time"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_schedule_events_end_time"), table_name="schedule_events")
    op.drop_index(op.f("ix_schedule_events_start_time"), table_name="schedule_events")
    op.drop_index(op.f("ix_schedule_events_user_id"), table_name="schedule_events")
    op.drop_index(op.f("ix_schedule_events_id"), table_name="schedule_events")
    op.drop_table("schedule_events")
