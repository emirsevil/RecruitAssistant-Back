"""add dashboard models

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dashboard_user_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("completed_interviews", sa.Integer(), nullable=False),
        sa.Column("avg_hr_score", sa.Integer(), nullable=True),
        sa.Column("avg_technical_score", sa.Integer(), nullable=True),
        sa.Column("cv_ats_score", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_dashboard_user_progress_id"), "dashboard_user_progress", ["id"], unique=False)
    op.create_index(op.f("ix_dashboard_user_progress_user_id"), "dashboard_user_progress", ["user_id"], unique=False)

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activity_logs_id"), "activity_logs", ["id"], unique=False)
    op.create_index(op.f("ix_activity_logs_user_id"), "activity_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_activity_logs_created_at"), "activity_logs", ["created_at"], unique=False)

    op.create_table(
        "skill_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skill_scores_id"), "skill_scores", ["id"], unique=False)
    op.create_index(op.f("ix_skill_scores_user_id"), "skill_scores", ["user_id"], unique=False)

    op.create_table(
        "weekly_goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("interviews_target", sa.Integer(), nullable=False),
        sa.Column("quizzes_target", sa.Integer(), nullable=False),
        sa.Column("practice_minutes_target", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_weekly_goals_id"), "weekly_goals", ["id"], unique=False)
    op.create_index(op.f("ix_weekly_goals_user_id"), "weekly_goals", ["user_id"], unique=False)
    op.create_index(op.f("ix_weekly_goals_week_start"), "weekly_goals", ["week_start"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_weekly_goals_week_start"), table_name="weekly_goals")
    op.drop_index(op.f("ix_weekly_goals_user_id"), table_name="weekly_goals")
    op.drop_index(op.f("ix_weekly_goals_id"), table_name="weekly_goals")
    op.drop_table("weekly_goals")

    op.drop_index(op.f("ix_skill_scores_user_id"), table_name="skill_scores")
    op.drop_index(op.f("ix_skill_scores_id"), table_name="skill_scores")
    op.drop_table("skill_scores")

    op.drop_index(op.f("ix_activity_logs_created_at"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_user_id"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_id"), table_name="activity_logs")
    op.drop_table("activity_logs")

    op.drop_index(op.f("ix_dashboard_user_progress_user_id"), table_name="dashboard_user_progress")
    op.drop_index(op.f("ix_dashboard_user_progress_id"), table_name="dashboard_user_progress")
    op.drop_table("dashboard_user_progress")
