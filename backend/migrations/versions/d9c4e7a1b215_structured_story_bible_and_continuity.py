"""add structured Story Bible entities and continuity findings

Revision ID: d9c4e7a1b215
Revises: c2712c048f9a
Create Date: 2026-11-05 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9c4e7a1b215"
down_revision: Union[str, None] = "c2712c048f9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _entity_columns() -> list[sa.Column]:
    return [
        sa.Column("source_type", sa.String(length=24), nullable=False, server_default="writer"),
        sa.Column("confirmation_status", sa.String(length=28), nullable=False, server_default="writer_confirmed"),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
    ]


def upgrade() -> None:
    op.add_column("scenes", sa.Column("timeline_position", sa.Integer(), nullable=True))
    op.add_column("scenes", sa.Column("timeline_context", sa.String(length=24), nullable=False, server_default="unspecified"))

    op.create_table(
        "story_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("aliases", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("goals", sa.Text(), nullable=False, server_default=""),
        sa.Column("motivations", sa.Text(), nullable=False, server_default=""),
        sa.Column("fears", sa.Text(), nullable=False, server_default=""),
        sa.Column("strengths", sa.Text(), nullable=False, server_default=""),
        sa.Column("weaknesses", sa.Text(), nullable=False, server_default=""),
        sa.Column("character_arc", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("status_effective_position", sa.Integer(), nullable=True),
        *_entity_columns(),
    )
    op.create_index("ix_story_characters_project_id", "story_characters", ["project_id"])

    op.create_table(
        "story_relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_a_id", sa.Integer(), sa.ForeignKey("story_characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_b_id", sa.Integer(), sa.ForeignKey("story_characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(length=80), nullable=False, server_default="unspecified"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        *_entity_columns(),
    )
    op.create_index("ix_story_relationships_project_id", "story_relationships", ["project_id"])
    op.create_index("ix_story_relationships_character_a_id", "story_relationships", ["character_a_id"])
    op.create_index("ix_story_relationships_character_b_id", "story_relationships", ["character_b_id"])

    op.create_table(
        "story_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("conflict_type", sa.String(length=32), nullable=False, server_default="unspecified"),
        sa.Column("objectives", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("stakes", sa.Text(), nullable=False, server_default=""),
        *_entity_columns(),
    )
    op.create_index("ix_story_conflicts_project_id", "story_conflicts", ["project_id"])

    op.create_table(
        "story_conflict_characters",
        sa.Column("conflict_id", sa.Integer(), sa.ForeignKey("story_conflicts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("story_characters.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "story_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("aliases", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("parent_location_id", sa.Integer(), sa.ForeignKey("story_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("characteristics", sa.Text(), nullable=False, server_default="[]"),
        *_entity_columns(),
    )
    op.create_index("ix_story_locations_project_id", "story_locations", ["project_id"])

    op.create_table(
        "story_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("story_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("timeline_position", sa.Integer(), nullable=True),
        sa.Column("date_text", sa.String(length=120), nullable=True),
        sa.Column("related_event_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("dependency_event_ids", sa.Text(), nullable=False, server_default="[]"),
        *_entity_columns(),
    )
    op.create_index("ix_story_events_project_id", "story_events", ["project_id"])
    op.create_index("ix_story_events_location_id", "story_events", ["location_id"])

    op.create_table(
        "story_event_characters",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("story_events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("story_characters.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "story_entity_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(length=24), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_story_entity_revisions_project_id", "story_entity_revisions", ["project_id"])
    op.create_index("ix_story_entity_revisions_entity_id", "story_entity_revisions", ["entity_id"])

    op.create_table(
        "continuity_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("finding_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("relevant_character_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("relevant_scene_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("disposition", sa.String(length=24), nullable=False, server_default="unreviewed"),
        sa.Column("writer_explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution_status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_continuity_finding_fingerprint"),
    )
    op.create_index("ix_continuity_findings_project_id", "continuity_findings", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_continuity_findings_project_id", table_name="continuity_findings")
    op.drop_table("continuity_findings")
    op.drop_index("ix_story_entity_revisions_entity_id", table_name="story_entity_revisions")
    op.drop_index("ix_story_entity_revisions_project_id", table_name="story_entity_revisions")
    op.drop_table("story_entity_revisions")
    op.drop_table("story_event_characters")
    op.drop_index("ix_story_events_location_id", table_name="story_events")
    op.drop_index("ix_story_events_project_id", table_name="story_events")
    op.drop_table("story_events")
    op.drop_index("ix_story_locations_project_id", table_name="story_locations")
    op.drop_table("story_locations")
    op.drop_table("story_conflict_characters")
    op.drop_index("ix_story_conflicts_project_id", table_name="story_conflicts")
    op.drop_table("story_conflicts")
    op.drop_index("ix_story_relationships_character_b_id", table_name="story_relationships")
    op.drop_index("ix_story_relationships_character_a_id", table_name="story_relationships")
    op.drop_index("ix_story_relationships_project_id", table_name="story_relationships")
    op.drop_table("story_relationships")
    op.drop_index("ix_story_characters_project_id", table_name="story_characters")
    op.drop_table("story_characters")
    op.drop_column("scenes", "timeline_context")
    op.drop_column("scenes", "timeline_position")
