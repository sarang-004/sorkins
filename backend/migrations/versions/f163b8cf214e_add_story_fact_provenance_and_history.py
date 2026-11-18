"""add Story Bible provenance and decision history

Revision ID: f163b8cf214e
Revises: a8e13c3f2edc
Create Date: 2026-11-04 11:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f163b8cf214e"
down_revision: Union[str, None] = "a8e13c3f2edc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "premise_questions",
        sa.Column("premise_snapshot", sa.Text(), server_default="", nullable=False),
    )
    op.execute(
        "UPDATE premise_questions SET premise_snapshot = "
        "(SELECT premise FROM projects WHERE projects.id = premise_questions.project_id)"
    )
    op.add_column(
        "premise_analyses",
        sa.Column("extractions", sa.Text(), server_default="[]", nullable=False),
    )
    op.add_column(
        "premise_analyses",
        sa.Column("analysis_mode", sa.String(length=20), server_default="ai", nullable=False),
    )
    op.add_column(
        "premise_analyses",
        sa.Column("analysis_notice", sa.Text(), nullable=True),
    )
    op.add_column("story_facts", sa.Column("original_value", sa.Text(), nullable=True))
    op.add_column(
        "story_facts",
        sa.Column("evidence", sa.Text(), server_default="", nullable=False),
    )
    op.add_column("story_facts", sa.Column("source_text", sa.Text(), nullable=True))
    op.add_column(
        "story_facts",
        sa.Column("writer_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "story_facts",
        sa.Column("intentionally_undecided", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "story_facts",
        sa.Column(
            "modified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute("UPDATE story_facts SET modified_at = CURRENT_TIMESTAMP WHERE modified_at IS NULL")
    with op.batch_alter_table("story_facts") as batch_op:
        batch_op.alter_column(
            "modified_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
    op.execute("UPDATE story_facts SET original_value = value")
    op.execute(
        "UPDATE story_facts SET writer_confirmed = 1 "
        "WHERE status = 'confirmed' AND lower(source) = 'writer'"
    )
    op.create_table(
        "story_fact_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("fact_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("evidence", sa.Text(), server_default="", nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("writer_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("intentionally_undecided", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fact_id"], ["story_facts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_story_fact_revisions_project_id"),
        "story_fact_revisions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_story_fact_revisions_fact_id"),
        "story_fact_revisions",
        ["fact_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_story_fact_revisions_fact_id"), table_name="story_fact_revisions")
    op.drop_index(op.f("ix_story_fact_revisions_project_id"), table_name="story_fact_revisions")
    op.drop_table("story_fact_revisions")
    op.drop_column("story_facts", "modified_at")
    op.drop_column("story_facts", "intentionally_undecided")
    op.drop_column("story_facts", "writer_confirmed")
    op.drop_column("story_facts", "source_text")
    op.drop_column("story_facts", "evidence")
    op.drop_column("story_facts", "original_value")
    op.drop_column("premise_analyses", "analysis_mode")
    op.drop_column("premise_analyses", "analysis_notice")
    op.drop_column("premise_analyses", "extractions")
    op.drop_column("premise_questions", "premise_snapshot")
