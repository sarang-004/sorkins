"""add status to structured story conflicts

Revision ID: b4e81d02c7a9
Revises: d9c4e7a1b215
Create Date: 2026-11-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e81d02c7a9"
down_revision: Union[str, None] = "d9c4e7a1b215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("story_conflicts", sa.Column("status", sa.String(length=24), nullable=False, server_default="active"))


def downgrade() -> None:
    op.drop_column("story_conflicts", "status")
