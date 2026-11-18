from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BlockType = Literal[
    "scene_heading", "action", "character", "dialogue", "parenthetical", "transition", "shot"
]
FactStatus = Literal["confirmed", "provisional", "inferred", "undecided"]


class BlockInput(BaseModel):
    id: int | None = None
    type: BlockType
    text: str = Field(default="", max_length=100_000)


class BlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: BlockType
    text: str
    position: int = Field(validation_alias="order_index")


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    act_id: int
    number: int = 0
    title: str
    description: str
    writer_notes: str
    completed: bool
    timeline_position: int | None
    timeline_context: Literal["present", "flashback", "dream", "alternate", "unreliable", "unspecified"]
    blocks: list[BlockRead]


class ActRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: int = Field(validation_alias="order_index")
    title: str
    scenes: list[SceneRead]


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    format: str
    genre: str
    runtime: str
    language: str
    premise: str
    setup_step: Literal["questions", "review", "complete"]
    updated_at: datetime
    acts: list[ActRead]


class ProjectCreate(BaseModel):
    title: str = Field(default="Untitled Screenplay", max_length=200)
    format: str = Field(default="Feature Film", max_length=40)
    genre: str = Field(default="", max_length=100)
    runtime: str = Field(default="", max_length=60)
    language: str = Field(default="English", max_length=60)
    premise: str = Field(default="", max_length=5_000)
    setup_flow: bool = False


class StorySetupAnswer(BaseModel):
    status: Literal["answered", "skipped", "undecided"] = "answered"
    response: str = Field(default="", max_length=5_000)


class StorySetupRead(BaseModel):
    step: Literal["questions", "review", "complete"]
    answers: dict[str, StorySetupAnswer]


class StorySetupUpdate(BaseModel):
    step: Literal["questions", "review", "complete"]
    answers: dict[str, StorySetupAnswer]


class TutorialState(BaseModel):
    welcome_dismissed: bool = False
    completed: dict[str, bool] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    format: str | None = Field(default=None, max_length=40)
    genre: str | None = Field(default=None, max_length=100)
    runtime: str | None = Field(default=None, max_length=60)
    language: str | None = Field(default=None, max_length=60)
    premise: str | None = Field(default=None, max_length=5_000)


class SceneUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    writer_notes: str | None = Field(default=None, max_length=10_000)
    completed: bool | None = None
    timeline_position: int | None = Field(default=None, ge=0)
    timeline_context: Literal["present", "flashback", "dream", "alternate", "unreliable", "unspecified"] | None = None
    blocks: list[BlockInput] | None = None


class ReorderRequest(BaseModel):
    direction: Literal["up", "down"] | None = None
    target_scene_id: int | None = None
    target_act_id: int | None = None

    @model_validator(mode="after")
    def require_one_move_target(self) -> "ReorderRequest":
        if sum(value is not None for value in (self.direction, self.target_scene_id, self.target_act_id)) != 1:
            raise ValueError("Specify exactly one direction, target scene, or target act.")
        return self


class StoryFactCreate(BaseModel):
    category: str = Field(default="Story fact", max_length=80)
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=5_000)
    status: FactStatus = "confirmed"
    source: str = Field(default="Writer", max_length=60)
    evidence: str = Field(default="", max_length=5_000)
    source_text: str | None = Field(default=None, max_length=5_000)
    writer_confirmed: bool = True
    intentionally_undecided: bool = False


class StoryFactUpdate(BaseModel):
    category: str = Field(default="Story fact", max_length=80)
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=5_000)
    status: FactStatus
    source: str = Field(default="Writer", max_length=60)
    evidence: str = Field(default="", max_length=5_000)
    source_text: str | None = Field(default=None, max_length=5_000)
    writer_confirmed: bool = True
    intentionally_undecided: bool = False


class StoryFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    label: str
    value: str
    status: FactStatus
    source: str
    original_value: str | None
    evidence: str
    source_text: str | None
    writer_confirmed: bool
    intentionally_undecided: bool
    modified_at: datetime


class StoryFactRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fact_id: int | None
    action: Literal["created", "updated", "deleted"]
    category: str
    label: str
    original_value: str | None
    value: str
    status: FactStatus
    source: str
    evidence: str
    source_text: str | None
    writer_confirmed: bool
    intentionally_undecided: bool
    changed_at: datetime


class PremiseMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "character",
        "character_name",
        "character_role",
        "character_description",
        "organization",
        "object",
        "event",
        "action",
        "time_reference",
        "relationship",
        "location",
        "motivation_or_goal",
    ]
    value: str = Field(min_length=1, max_length=2_000)
    status: Literal["EXPLICIT"] = "EXPLICIT"
    evidence: str = Field(min_length=1, max_length=2_000)
    source: Literal["premise"] = "premise"
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    extraction_method: Literal["regex"] = "regex"
    confirmation_status: Literal["unconfirmed", "writer_confirmed"] = "unconfirmed"
    confidence: float = Field(default=1.0, ge=0, le=1)
    explanation: str = "Directly stated in the cited premise text."

    @model_validator(mode="after")
    def require_literal_evidence(self) -> "PremiseMention":
        if self.value not in self.evidence:
            raise ValueError("Extracted values must be contained in their evidence.")
        return self

    @model_validator(mode="after")
    def validate_source_span(self) -> "PremiseMention":
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("Source start and end must either both be provided or both be omitted.")
        if self.source_start is not None and self.source_end is not None and self.source_end < self.source_start:
            raise ValueError("Source end must not precede source start.")
        return self


class AssistantRequest(BaseModel):
    scene_id: int | None = None
    prompt: str = Field(min_length=1, max_length=4_000)


class AssistantResponse(BaseModel):
    response: str
    model: str


NarrativeStatus = Literal["EXPLICIT", "INFERRED", "UNDECIDED", "NOT_APPLICABLE"]
PremiseQuestionStatus = Literal[
    "pending", "answered", "skipped", "undecided", "not_applicable", "superseded"
]
NarrativeElementKey = Literal[
    "protagonist",
    "antagonist",
    "central_conflict",
    "external_conflict",
    "internal_conflict",
    "character_motivations",
    "character_goals",
    "stakes",
    "genre",
    "setting",
    "theme",
    "central_dramatic_question",
    "important_relationships",
    "potential_structure",
]


class NarrativeElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None
    status: NarrativeStatus
    evidence: str = Field(min_length=1, max_length=1_000)
    source: Literal["premise", "writer", "ai_inference"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    explanation: str = Field(default="", max_length=1_000)
    writer_confirmed: bool = False
    intentionally_undecided: bool = False

    @model_validator(mode="after")
    def validate_status_value(self) -> "NarrativeElement":
        if self.status == "UNDECIDED" and self.value is not None:
            raise ValueError("Undecided narrative elements must not include a value.")
        if self.status == "NOT_APPLICABLE" and self.value is not None:
            raise ValueError("Not-applicable narrative elements must not include a value.")
        if self.status in {"EXPLICIT", "INFERRED"} and not (self.value and self.value.strip()):
            raise ValueError("Explicit and inferred elements require a value.")
        if not self.evidence.strip():
            raise ValueError("Every narrative element requires supporting evidence.")
        if not self.explanation.strip():
            self.explanation = {
                "EXPLICIT": "Directly stated in the cited source text.",
                "INFERRED": "This is an interpretation, not a confirmed fact.",
                "UNDECIDED": "The available source does not establish this information.",
                "NOT_APPLICABLE": "The source establishes that this element does not apply.",
            }[self.status]
        if self.confidence is None:
            self.confidence = {
                "EXPLICIT": 1.0,
                "INFERRED": 0.5,
                "UNDECIDED": 0.0,
                "NOT_APPLICABLE": 1.0,
            }[self.status]
        self.writer_confirmed = (
            self.source == "writer"
            and self.status in {"EXPLICIT", "NOT_APPLICABLE"}
        )
        self.intentionally_undecided = (
            self.source == "writer" and self.status == "UNDECIDED"
        )
        return self


class NarrativeElements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protagonist: NarrativeElement
    antagonist: NarrativeElement
    central_conflict: NarrativeElement
    external_conflict: NarrativeElement
    internal_conflict: NarrativeElement
    character_motivations: NarrativeElement
    character_goals: NarrativeElement
    stakes: NarrativeElement
    genre: NarrativeElement
    setting: NarrativeElement
    theme: NarrativeElement
    central_dramatic_question: NarrativeElement
    important_relationships: NarrativeElement
    potential_structure: NarrativeElement


AntagonistClassification = Literal[
    "explicit_antagonist",
    "potential_antagonist",
    "antagonistic_force",
    "undecided",
    "no_conventional_antagonist",
]


class PremiseAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise: str
    narrative_elements: NarrativeElements
    antagonist_classification: AntagonistClassification = "undecided"


class PremiseQuestionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_key: NarrativeElementKey
    question: str = Field(min_length=8, max_length=500)

    @field_validator("question")
    @classmethod
    def require_one_open_question(cls, value: str) -> str:
        opening_word = value.strip().lower().split(maxsplit=1)[0].strip(".,:;")
        lower_value = value.lower()
        suggests_answers = any(
            phrase in lower_value
            for phrase in ("for example", "such as", "perhaps", "maybe", "would you prefer", "could it be")
        )
        if (
            value.count("?") != 1
            or " or " in lower_value
            or suggests_answers
            or opening_word not in {"what", "how", "who", "when", "where"}
        ):
            raise ValueError("Ask exactly one open question without listing suggested answers.")
        return value


class PremiseQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    element_key: NarrativeElementKey
    question: str
    premise_snapshot: str
    status: PremiseQuestionStatus
    response: str
    created_at: datetime
    answered_at: datetime | None


class PremiseGap(BaseModel):
    element_key: NarrativeElementKey
    importance: Literal["CRITICAL", "IMPORTANT", "OPTIONAL"]


class FoundationElement(BaseModel):
    key: str
    label: str
    status: Literal[
        "established", "partially_established", "undecided", "intentionally_deferred", "not_applicable"
    ]
    explanation: str
    next_consideration: str | None = None


class PremiseDevelopmentRead(BaseModel):
    analysis: PremiseAnalysisResult | None
    conversation: list[PremiseQuestionRead]
    current_question: PremiseQuestionRead | None
    extractions: list[PremiseMention] = Field(default_factory=list)
    gaps: list[PremiseGap] = Field(default_factory=list)
    foundation: list[FoundationElement] = Field(default_factory=list)
    analysis_mode: Literal["ai", "deterministic"] | None = None
    analysis_notice: str | None = None


EntitySource = Literal["writer", "premise", "screenplay", "ai_inference"]
ConfirmationStatus = Literal["writer_confirmed", "explicit_unconfirmed", "inferred_unconfirmed", "undecided"]


class EntityProvenance(BaseModel):
    source_type: EntitySource = "writer"
    confirmation_status: ConfirmationStatus = "writer_confirmed"
    evidence: str = Field(default="", max_length=5_000)
    source_text: str | None = Field(default=None, max_length=10_000)
    source_refs: list[dict[str, object]] = Field(default_factory=list)


class CharacterInput(EntityProvenance):
    name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=5_000)
    role: str = Field(default="", max_length=100)
    goals: str = Field(default="", max_length=5_000)
    motivations: str = Field(default="", max_length=5_000)
    fears: str = Field(default="", max_length=5_000)
    strengths: str = Field(default="", max_length=5_000)
    weaknesses: str = Field(default="", max_length=5_000)
    character_arc: str = Field(default="", max_length=5_000)
    current_status: str = Field(default="unknown", max_length=32)
    status_effective_position: int | None = Field(default=None, ge=0)


class CharacterRead(CharacterInput):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime


class EntityMergeRequest(BaseModel):
    target_id: int = Field(gt=0)


class RelationshipInput(EntityProvenance):
    character_a_id: int = Field(gt=0)
    character_b_id: int = Field(gt=0)
    relationship_type: str = Field(default="unspecified", max_length=80)
    description: str = Field(default="", max_length=5_000)

    @model_validator(mode="after")
    def require_two_characters(self) -> "RelationshipInput":
        if self.character_a_id == self.character_b_id:
            raise ValueError("A relationship must connect two different characters.")
        return self


class RelationshipRead(RelationshipInput):
    id: int
    project_id: int
    character_a_name: str
    character_b_name: str
    created_at: datetime
    updated_at: datetime


class ConflictInput(EntityProvenance):
    description: str = Field(min_length=1, max_length=5_000)
    conflict_type: Literal["internal", "interpersonal", "societal", "environmental", "organisational", "other", "unspecified"] = "unspecified"
    status: Literal["active", "paused", "resolved", "unknown"] = "active"
    character_ids: list[int] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    stakes: str = Field(default="", max_length=5_000)


class ConflictRead(ConflictInput):
    id: int
    project_id: int
    characters: list[CharacterRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class LocationInput(EntityProvenance):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5_000)
    aliases: list[str] = Field(default_factory=list)
    parent_location_id: int | None = Field(default=None, gt=0)
    characteristics: list[str] = Field(default_factory=list)


class LocationRead(LocationInput):
    id: int
    project_id: int
    parent_location_name: str | None = None
    created_at: datetime
    updated_at: datetime


class StoryEventInput(EntityProvenance):
    description: str = Field(min_length=1, max_length=5_000)
    character_ids: list[int] = Field(default_factory=list)
    location_id: int | None = Field(default=None, gt=0)
    timeline_position: int | None = Field(default=None, ge=0)
    date_text: str | None = Field(default=None, max_length=120)
    related_event_ids: list[int] = Field(default_factory=list)
    dependency_event_ids: list[int] = Field(default_factory=list)


class StoryEventRead(StoryEventInput):
    id: int
    project_id: int
    character_names: list[str] = Field(default_factory=list)
    location_name: str | None = None
    created_at: datetime
    updated_at: datetime


class StoryEntityRevisionRead(BaseModel):
    id: int
    entity_type: str
    entity_id: int | None
    action: Literal["created", "updated", "deleted", "merged"]
    snapshot: dict[str, object]
    changed_at: datetime


class ContinuityFindingRead(BaseModel):
    id: int
    finding_type: str
    description: str
    severity: Literal["info", "warning", "important"]
    confidence: float
    relevant_character_ids: list[int]
    relevant_scene_ids: list[int]
    evidence_refs: list[dict[str, object]]
    disposition: Literal["unreviewed", "accepted_intentional", "needs_correction", "explained", "dismissed"]
    writer_explanation: str
    resolution_status: Literal["open", "resolved"]
    detected_at: datetime


class ContinuityDispositionUpdate(BaseModel):
    disposition: Literal["accepted_intentional", "needs_correction", "explained", "dismissed", "unreviewed"]
    writer_explanation: str = Field(default="", max_length=5_000)


class ContinuityAnalysisResult(BaseModel):
    findings: list[ContinuityFindingRead]
    analyzed_scenes: int
    message: str


class PremiseAnswerRequest(BaseModel):
    status: Literal["answered", "skipped", "undecided", "not_applicable"]
    response: str = Field(default="", max_length=2_000)


class PremiseElementUpdate(BaseModel):
    status: Literal["EXPLICIT", "INFERRED", "UNDECIDED", "NOT_APPLICABLE"]
    value: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_status_value(self) -> "PremiseElementUpdate":
        if self.status in {"EXPLICIT", "INFERRED"} and not (self.value and self.value.strip()):
            raise ValueError("Explicit and inferred elements require a value.")
        if self.status in {"UNDECIDED", "NOT_APPLICABLE"} and self.value is not None:
            raise ValueError("Undecided and not-applicable elements must not include a value.")
        return self
