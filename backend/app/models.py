from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled Screenplay")
    format: Mapped[str] = mapped_column(String(40), default="Feature Film")
    genre: Mapped[str] = mapped_column(String(100), default="")
    runtime: Mapped[str] = mapped_column(String(60), default="")
    language: Mapped[str] = mapped_column(String(60), default="English")
    premise: Mapped[str] = mapped_column(Text, default="")
    setup_step: Mapped[str] = mapped_column(String(20), default="complete")
    setup_answers: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    acts: Mapped[list["Act"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Act.order_index"
    )
    facts: Mapped[list["StoryFact"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    fact_revisions: Mapped[list["StoryFactRevision"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="StoryFactRevision.id"
    )
    premise_analysis: Mapped["PremiseAnalysis | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    premise_questions: Mapped[list["PremiseQuestion"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="PremiseQuestion.id"
    )
    characters: Mapped[list["Character"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    relationships: Mapped[list["StoryRelationship"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    conflicts: Mapped[list["StoryConflict"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    locations: Mapped[list["Location"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    story_events: Mapped[list["StoryEvent"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    continuity_findings: Mapped[list["ContinuityFinding"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Act(Base):
    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100), default="ACT I")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    project: Mapped[Project] = relationship(back_populates="acts")
    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="act", cascade="all, delete-orphan", order_by="Scene.order_index"
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="INT. LOCATION - DAY")
    description: Mapped[str] = mapped_column(Text, default="")
    writer_notes: Mapped[str] = mapped_column(Text, default="")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    timeline_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeline_context: Mapped[str] = mapped_column(String(24), default="unspecified")
    act: Mapped[Act] = relationship(back_populates="scenes")
    blocks: Mapped[list["ScreenplayBlock"]] = relationship(
        back_populates="scene", cascade="all, delete-orphan", order_by="ScreenplayBlock.order_index"
    )


class ScreenplayBlock(Base):
    __tablename__ = "screenplay_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30), default="action")
    text: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    scene: Mapped[Scene] = relationship(back_populates="blocks")


class StoryFact(Base):
    __tablename__ = "story_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(80), default="Story fact")
    label: Mapped[str] = mapped_column(String(160))
    value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    source: Mapped[str] = mapped_column(String(60), default="Writer")
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    writer_confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    intentionally_undecided: Mapped[bool] = mapped_column(Boolean, default=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    project: Mapped[Project] = relationship(back_populates="facts")
    revisions: Mapped[list["StoryFactRevision"]] = relationship(
        back_populates="fact", cascade="save-update, merge"
    )


class StoryFactRevision(Base):
    __tablename__ = "story_fact_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("story_facts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(160))
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(60))
    evidence: Mapped[str] = mapped_column(Text, default="")
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    writer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    intentionally_undecided: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    project: Mapped[Project] = relationship(back_populates="fact_revisions")
    fact: Mapped[StoryFact | None] = relationship(back_populates="revisions")


class PremiseAnalysis(Base):
    __tablename__ = "premise_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    premise_snapshot: Mapped[str] = mapped_column(Text)
    narrative_elements: Mapped[str] = mapped_column(Text)
    extractions: Mapped[str] = mapped_column(Text, default="[]")
    analysis_mode: Mapped[str] = mapped_column(String(20), default="ai")
    analysis_notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    project: Mapped[Project] = relationship(back_populates="premise_analysis")


class PremiseQuestion(Base):
    __tablename__ = "premise_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    element_key: Mapped[str] = mapped_column(String(60))
    question: Mapped[str] = mapped_column(Text)
    premise_snapshot: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped[Project] = relationship(back_populates="premise_questions")


class AppPreference(Base):
    __tablename__ = "app_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    tutorial_state: Mapped[str] = mapped_column(Text, default="{}")


conflict_characters = Table(
    "story_conflict_characters",
    Base.metadata,
    Column("conflict_id", ForeignKey("story_conflicts.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", ForeignKey("story_characters.id", ondelete="CASCADE"), primary_key=True),
)

event_characters = Table(
    "story_event_characters",
    Base.metadata,
    Column("event_id", ForeignKey("story_events.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", ForeignKey("story_characters.id", ondelete="CASCADE"), primary_key=True),
)


class NarrativeProvenance:
    source_type: Mapped[str] = mapped_column(String(24), default="writer")
    confirmation_status: Mapped[str] = mapped_column(String(28), default="writer_confirmed")
    evidence: Mapped[str] = mapped_column(Text, default="")
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Character(NarrativeProvenance, Base):
    __tablename__ = "story_characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    aliases: Mapped[str] = mapped_column(Text, default="[]")
    description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(100), default="")
    goals: Mapped[str] = mapped_column(Text, default="")
    motivations: Mapped[str] = mapped_column(Text, default="")
    fears: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    character_arc: Mapped[str] = mapped_column(Text, default="")
    current_status: Mapped[str] = mapped_column(String(32), default="unknown")
    status_effective_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project: Mapped[Project] = relationship(back_populates="characters")
    as_character_a: Mapped[list["StoryRelationship"]] = relationship(
        foreign_keys="StoryRelationship.character_a_id", back_populates="character_a", cascade="all, delete-orphan"
    )
    as_character_b: Mapped[list["StoryRelationship"]] = relationship(
        foreign_keys="StoryRelationship.character_b_id", back_populates="character_b", cascade="all, delete-orphan"
    )
    conflicts: Mapped[list["StoryConflict"]] = relationship(secondary=conflict_characters, back_populates="characters")
    events: Mapped[list["StoryEvent"]] = relationship(secondary=event_characters, back_populates="characters")


class StoryRelationship(NarrativeProvenance, Base):
    __tablename__ = "story_relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    character_a_id: Mapped[int] = mapped_column(ForeignKey("story_characters.id", ondelete="CASCADE"), index=True)
    character_b_id: Mapped[int] = mapped_column(ForeignKey("story_characters.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(80), default="unspecified")
    description: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[Project] = relationship(back_populates="relationships")
    character_a: Mapped[Character] = relationship(foreign_keys=[character_a_id], back_populates="as_character_a")
    character_b: Mapped[Character] = relationship(foreign_keys=[character_b_id], back_populates="as_character_b")


class StoryConflict(NarrativeProvenance, Base):
    __tablename__ = "story_conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    conflict_type: Mapped[str] = mapped_column(String(32), default="unspecified")
    status: Mapped[str] = mapped_column(String(24), default="active")
    objectives: Mapped[str] = mapped_column(Text, default="[]")
    stakes: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[Project] = relationship(back_populates="conflicts")
    characters: Mapped[list[Character]] = relationship(secondary=conflict_characters, back_populates="conflicts")


class Location(NarrativeProvenance, Base):
    __tablename__ = "story_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    aliases: Mapped[str] = mapped_column(Text, default="[]")
    parent_location_id: Mapped[int | None] = mapped_column(ForeignKey("story_locations.id", ondelete="SET NULL"), nullable=True)
    characteristics: Mapped[str] = mapped_column(Text, default="[]")
    project: Mapped[Project] = relationship(back_populates="locations")
    parent: Mapped["Location | None"] = relationship(remote_side="Location.id")


class StoryEvent(NarrativeProvenance, Base):
    __tablename__ = "story_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("story_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    timeline_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    related_event_ids: Mapped[str] = mapped_column(Text, default="[]")
    dependency_event_ids: Mapped[str] = mapped_column(Text, default="[]")
    project: Mapped[Project] = relationship(back_populates="story_events")
    location: Mapped[Location | None] = relationship()
    characters: Mapped[list[Character]] = relationship(secondary=event_characters, back_populates="events")


class StoryEntityRevision(Base):
    __tablename__ = "story_entity_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(24))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(16))
    snapshot: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContinuityFinding(Base):
    __tablename__ = "continuity_findings"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint", name="uq_continuity_finding_fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    finding_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    confidence: Mapped[float] = mapped_column(default=0.8)
    relevant_character_ids: Mapped[str] = mapped_column(Text, default="[]")
    relevant_scene_ids: Mapped[str] = mapped_column(Text, default="[]")
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]")
    disposition: Mapped[str] = mapped_column(String(24), default="unreviewed")
    writer_explanation: Mapped[str] = mapped_column(Text, default="")
    resolution_status: Mapped[str] = mapped_column(String(20), default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    project: Mapped[Project] = relationship(back_populates="continuity_findings")
