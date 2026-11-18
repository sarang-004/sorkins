"""persist guided setup and tutorial progress

Revision ID: c2712c048f9a
Revises: f163b8cf214e
Create Date: 2026-11-05 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2712c048f9a"
down_revision: Union[str, None] = "f163b8cf214e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("setup_step", sa.String(length=20), server_default="complete", nullable=False),
    )
    op.add_column(
        "projects",
        sa.Column("setup_answers", sa.Text(), server_default="{}", nullable=False),
    )
    op.create_table(
        "app_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tutorial_state", sa.Text(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("app_preferences")
    op.drop_column("projects", "setup_answers")
    op.drop_column("projects", "setup_step")
