import json
import os
import re
import asyncio
from pathlib import Path
from datetime import datetime, timezone

import httpx
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import database_url, get_db
from .models import (
    Act,
    AppPreference,
    Character,
    ContinuityFinding,
    Location,
    PremiseAnalysis,
    PremiseQuestion,
    Project,
    Scene,
    ScreenplayBlock,
    StoryFact,
    StoryFactRevision,
    StoryConflict,
    StoryEntityRevision,
    StoryEvent,
    StoryRelationship,
)
from .narrative.analysis import deterministic_analysis
from .narrative.gaps import gap_records, next_gap
from .narrative.foundation import assess_foundation
from .narrative.continuity import detect_continuity_candidates
from .narrative.parser import parse_premise
from .narrative.provider import OllamaProvider
from .narrative.questions import offline_question
from .narrative.validation import validate_analysis
from .prompts import PREMISE_ANALYSIS_PROMPT, SYSTEM_PROMPT
from .schemas import (
    AssistantRequest,
    AssistantResponse,
    BlockInput,
    CharacterInput,
    CharacterRead,
    EntityMergeRequest,
    FactStatus,
    ConflictInput,
    ConflictRead,
    ContinuityAnalysisResult,
    ContinuityDispositionUpdate,
    ContinuityFindingRead,
    LocationInput,
    LocationRead,
    NarrativeElement,
    PremiseAnalysisResult,
    PremiseAnswerRequest,
    PremiseDevelopmentRead,
    PremiseElementUpdate,
    PremiseQuestionRead,
    PremiseMention,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ReorderRequest,
    SceneRead,
    SceneUpdate,
    StoryFactCreate,
    StoryFactRead,
    StoryFactRevisionRead,
    StoryFactUpdate,
    StoryEntityRevisionRead,
    StoryEventInput,
    StoryEventRead,
    RelationshipInput,
    RelationshipRead,
    StorySetupRead,
    StorySetupUpdate,
    TutorialState,
)

backend_dir = Path(__file__).resolve().parents[1]
migration_config = Config(str(backend_dir / "alembic.ini"))
migration_config.set_main_option("script_location", str(backend_dir / "migrations"))
migration_config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
command.upgrade(migration_config, "head")

app = FastAPI(title="Sorkins local screenplay service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_project(db: Session, project_id: int) -> Project:
    statement = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.acts).selectinload(Act.scenes).selectinload(Scene.blocks))
    )
    project = db.scalar(statement)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def project_read(db: Session, project_id: int) -> ProjectRead:
    project = get_project(db, project_id)
    result = ProjectRead.model_validate(project)
    scene_number = 1
    for act in result.acts:
        for scene in act.scenes:
            scene.number = scene_number
            scene_number += 1
    return result


def get_scene(db: Session, project_id: int, scene_id: int) -> Scene:
    scene = db.scalar(
        select(Scene)
        .join(Act)
        .where(Scene.id == scene_id, Act.project_id == project_id)
        .options(selectinload(Scene.blocks), selectinload(Scene.act))
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found in this project.")
    return scene


def renumber_scenes(db: Session, project_id: int) -> None:
    project = get_project(db, project_id)
    for act in project.acts:
        for index, scene in enumerate(act.scenes):
            scene.order_index = index


def reconcile_blocks(scene: Scene, incoming: list[BlockInput]) -> None:
    existing = {block.id: block for block in scene.blocks}
    retained: list[ScreenplayBlock] = []
    for index, item in enumerate(incoming):
        if item.id is not None and item.id in existing:
            block = existing[item.id]
            block.type = item.type
            block.text = item.text
        else:
            block = ScreenplayBlock(type=item.type, text=item.text, order_index=index)
        block.order_index = index
        retained.append(block)
    scene.blocks = retained


NARRATIVE_LABELS = {
    "protagonist": "Protagonist",
    "antagonist": "Antagonistic force",
    "central_conflict": "Central conflict",
    "external_conflict": "External conflict",
    "internal_conflict": "Internal conflict",
    "character_motivations": "Character motivations",
    "character_goals": "Character goals",
    "stakes": "Stakes",
    "genre": "Genre",
    "setting": "Setting",
    "theme": "Theme",
    "central_dramatic_question": "Central dramatic question",
    "important_relationships": "Important relationships",
    "potential_structure": "Potential structure",
}

SETUP_QUESTION_ELEMENTS = {
    "protagonist": "protagonist",
    "goal": "character_goals",
    "motivation": "character_motivations",
    "obstacles": "central_conflict",
    "stakes": "stakes",
    "opposition": "antagonist",
    "opposition-goal": "antagonist",
    "conflicting-goals": "central_conflict",
    "opposition-kind": "antagonist",
    "central-conflict": "central_conflict",
    "failure": "stakes",
    "difficulty": "external_conflict",
    "conflict-kind": "external_conflict",
    "supporting-characters": "important_relationships",
    "supporting-roles": "important_relationships",
    "relationships": "important_relationships",
    "location": "setting",
    "time": "setting",
    "world-details": "setting",
    "dramatic-question": "central_dramatic_question",
    "journey": "potential_structure",
    "ending": "potential_structure",
}

class OllamaInvalidResponse(RuntimeError):
    pass


def _ollama_timeout() -> httpx.Timeout:
    try:
        values = {
            "connect": float(os.environ.get("OLLAMA_CONNECT_TIMEOUT_SECONDS", "10")),
            "read": float(os.environ.get("OLLAMA_READ_TIMEOUT_SECONDS", "1800")),
            "write": float(os.environ.get("OLLAMA_WRITE_TIMEOUT_SECONDS", "60")),
        }
    except ValueError as error:
        raise RuntimeError(
            "OLLAMA_CONNECT_TIMEOUT_SECONDS, OLLAMA_READ_TIMEOUT_SECONDS, and "
            "OLLAMA_WRITE_TIMEOUT_SECONDS must be valid numbers."
        ) from error
    if any(value <= 0 for value in values.values()):
        raise RuntimeError("Ollama timeout settings must be positive numbers.")
    return httpx.Timeout(connect=values["connect"], read=values["read"], write=values["write"], pool=values["connect"])


def _ollama_error(status_code: int, details: str, model: str) -> RuntimeError:
    if status_code == 404 and ("model" in details.lower() or "not found" in details.lower()):
        return RuntimeError(
            f"Ollama model '{model}' is not installed. Install it with `ollama pull {model}`, "
            "or select an installed model in OLLAMA_MODEL."
        )
    return RuntimeError(f"Ollama returned HTTP {status_code}: {details[:500]}")


def _raise_ollama_transport_error(
    error: Exception,
    base_url: str,
    model: str,
    received_data: bool,
    model_loaded: bool = False,
) -> RuntimeError:
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
        return RuntimeError(
            f"Cannot connect to Ollama at {base_url}. Confirm Ollama is running and reachable."
        )
    if isinstance(error, httpx.ReadTimeout):
        if received_data or model_loaded:
            return RuntimeError(
                "Ollama is reachable and the model is loaded, but inference did not complete before "
                "the timeout. This is an inference timeout, not a connection failure."
            )
        return RuntimeError(
            f"Connected to Ollama, but model '{model}' did not start responding before the "
            "inference timeout. The model may still be loading; retry in a moment."
        )
    if isinstance(error, httpx.TimeoutException):
        return RuntimeError(f"Ollama request timed out while communicating with {base_url}.")
    return RuntimeError(f"Could not communicate with Ollama at {base_url}: {error}")


def _ollama_model_loaded(client: httpx.Client, base_url: str, model: str, context_length: int) -> bool:
    timeout = _ollama_timeout()
    status_timeout = httpx.Timeout(
        connect=timeout.connect,
        read=min(timeout.read, 10),
        write=timeout.write,
        pool=timeout.pool,
    )
    try:
        response = client.get(f"{base_url}/api/ps", timeout=status_timeout)
    except (httpx.HTTPError, OSError) as error:
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
            raise _raise_ollama_transport_error(error, base_url, model, False) from error
        raise RuntimeError(
            f"Connected to Ollama at {base_url}, but could not check whether model '{model}' is loaded: {error}"
        ) from error
    if response.is_error:
        raise RuntimeError(f"Ollama model status check returned HTTP {response.status_code}.")
    try:
        models = response.json().get("models")
    except (ValueError, AttributeError) as error:
        raise OllamaInvalidResponse("Ollama returned an invalid model-status response.") from error
    if not isinstance(models, list):
        raise OllamaInvalidResponse("Ollama returned an invalid model-status response.")
    return any(
        isinstance(item, dict)
        and item.get("name") == model
        and isinstance(item.get("context_length"), int)
        and item["context_length"] >= context_length
        for item in models
    )


async def _ollama_model_loaded_async(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    context_length: int,
) -> bool:
    timeout = _ollama_timeout()
    status_timeout = httpx.Timeout(
        connect=timeout.connect,
        read=min(timeout.read, 10),
        write=timeout.write,
        pool=timeout.pool,
    )
    try:
        response = await client.get(f"{base_url}/api/ps", timeout=status_timeout)
    except (httpx.HTTPError, OSError) as error:
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
            raise _raise_ollama_transport_error(error, base_url, model, False) from error
        raise RuntimeError(
            f"Connected to Ollama at {base_url}, but could not check whether model '{model}' is loaded: {error}"
        ) from error
    if response.is_error:
        raise RuntimeError(f"Ollama model status check returned HTTP {response.status_code}.")
    try:
        models = response.json().get("models")
    except (ValueError, AttributeError) as error:
        raise OllamaInvalidResponse("Ollama returned an invalid model-status response.") from error
    if not isinstance(models, list):
        raise OllamaInvalidResponse("Ollama returned an invalid model-status response.")
    return any(
        isinstance(item, dict)
        and item.get("name") == model
        and isinstance(item.get("context_length"), int)
        and item["context_length"] >= context_length
        for item in models
    )


def _ollama_payload(
    messages: list[dict[str, str]],
    model: str,
    *,
    num_predict: int,
    num_gpu: int,
    response_schema: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        context_length = int(os.environ.get("OLLAMA_NUM_CTX", "6144"))
    except ValueError as error:
        raise RuntimeError("OLLAMA_NUM_CTX must be a valid integer.") from error
    if context_length <= 0:
        raise RuntimeError("OLLAMA_NUM_CTX must be a positive integer.")
    think_mode = os.environ.get("OLLAMA_THINK_MODE", "low").strip().lower()
    if think_mode not in {"false", "true", "low", "medium", "high"}:
        raise RuntimeError("OLLAMA_THINK_MODE must be false, true, low, medium, or high.")
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": {"false": False, "true": True}.get(think_mode, think_mode),
        "options": {
            "temperature": 0.1,
            "num_ctx": context_length,
            "num_predict": num_predict,
            "num_gpu": num_gpu,
        },
        "keep_alive": "5m",
    }
    if response_schema is not None:
        payload["format"] = response_schema
    return payload


def _ollama_json(
    messages: list[dict[str, str]],
    schema: dict[str, object],
    num_predict: int | None = None,
) -> dict[str, object]:
    base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen3-vl:4b")
    try:
        configured_gpu_layers = max(0, int(os.environ.get("OLLAMA_NUM_GPU", "0")))
        output_limit = num_predict if num_predict is not None else int(os.environ.get("OLLAMA_NUM_PREDICT", "4096"))
    except ValueError as error:
        raise RuntimeError("OLLAMA_NUM_GPU and OLLAMA_NUM_PREDICT must be valid integers.") from error
    if output_limit <= 0:
        raise RuntimeError("OLLAMA_NUM_PREDICT must be a positive integer.")
    payload = _ollama_payload(
        messages,
        model,
        num_predict=output_limit,
        num_gpu=configured_gpu_layers,
        response_schema=schema,
    )
    content_parts: list[str] = []
    received_data = False
    done_reason: str | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    try:
        context_length = int(os.environ.get("OLLAMA_NUM_CTX", "6144"))
    except ValueError as error:
        raise RuntimeError("OLLAMA_NUM_CTX must be a valid integer.") from error
    model_loaded = False
    try:
        with httpx.Client(timeout=_ollama_timeout()) as client:
            model_loaded = _ollama_model_loaded(client, base_url, model, context_length)
            with client.stream("POST", f"{base_url}/api/chat", json=payload) as response:
                if response.is_error:
                    raise _ollama_error(response.status_code, response.read().decode("utf-8", errors="replace"), model)
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise OllamaInvalidResponse("Ollama returned an invalid streaming response.") from error
                    received_data = True
                    if isinstance(item, dict) and isinstance(item.get("error"), str):
                        message = item["error"]
                        if "not found" in message.lower() and "model" in message.lower():
                            raise _ollama_error(404, message, model)
                        raise RuntimeError(f"Ollama reported an error: {message}")
                    message = item.get("message") if isinstance(item, dict) else None
                    chunk = message.get("content") if isinstance(message, dict) else None
                    if isinstance(chunk, str):
                        content_parts.append(chunk)
                    if isinstance(item, dict) and item.get("done") is True:
                        reason = item.get("done_reason")
                        done_reason = reason if isinstance(reason, str) else None
                        prompt_count = item.get("prompt_eval_count")
                        output_count = item.get("eval_count")
                        prompt_eval_count = prompt_count if isinstance(prompt_count, int) else None
                        eval_count = output_count if isinstance(output_count, int) else None
    except (httpx.HTTPError, OSError) as error:
        raise _raise_ollama_transport_error(
            error, base_url, model, received_data, model_loaded
        ) from error
    if done_reason == "length":
        if (
            prompt_eval_count is not None
            and eval_count is not None
            and prompt_eval_count + eval_count >= context_length
        ):
            raise OllamaInvalidResponse(
                f"Ollama reached the configured {context_length}-token context window before completing "
                "the structured response. Increase OLLAMA_NUM_CTX or use a shorter premise."
            )
        raise OllamaInvalidResponse(
            f"Ollama reached the {output_limit}-token output limit before completing the structured response. "
            "Increase OLLAMA_NUM_PREDICT or use a shorter premise."
        )
    content = "".join(content_parts).strip()
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as error:
        raise OllamaInvalidResponse(
            "Ollama returned invalid JSON. Retry the analysis or choose another model."
        ) from error
    if not isinstance(parsed, dict):
        raise OllamaInvalidResponse("Ollama returned an invalid structured response.")
    return parsed


def _ground_analysis_to_premise(analysis: PremiseAnalysisResult) -> PremiseAnalysisResult:
    return validate_analysis(analysis)


def _analysis_from_db(record: PremiseAnalysis) -> PremiseAnalysisResult:
    try:
        return PremiseAnalysisResult.model_validate_json(record.narrative_elements)
    except (ValidationError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Saved premise analysis is invalid. Reanalyze the premise to restore it.",
        ) from error


def _analysis_with_story_facts(db: Session, project_id: int, analysis: PremiseAnalysisResult) -> PremiseAnalysisResult:
    result = analysis.model_copy(deep=True)
    facts = db.scalars(select(StoryFact).where(StoryFact.project_id == project_id)).all()
    for fact in facts:
        if fact.status != "confirmed" or not fact.writer_confirmed or fact.intentionally_undecided:
            continue
        element_key = next(
            (key for key, label in NARRATIVE_LABELS.items() if label.casefold() == fact.label.casefold()),
            None,
        )
        if element_key and getattr(result.narrative_elements, element_key).source != "writer":
            setattr(result.narrative_elements, element_key, NarrativeElement(
                value=fact.value,
                status="EXPLICIT",
                evidence=fact.evidence or fact.value,
                source="writer",
                confidence=1.0,
                explanation="Recorded in the editable Story Bible.",
                writer_confirmed=True,
            ))
    return result


def _development_state(db: Session, project_id: int) -> PremiseDevelopmentRead:
    project = db.get(Project, project_id)
    analysis_record = db.scalar(
        select(PremiseAnalysis).where(PremiseAnalysis.project_id == project_id)
    )
    questions = db.scalars(
        select(PremiseQuestion)
        .where(PremiseQuestion.project_id == project_id)
        .order_by(PremiseQuestion.id)
    ).all()
    current_snapshot = project.premise if project else ""
    current = next(
        (
            question for question in questions
            if question.status == "pending" and question.premise_snapshot == current_snapshot
        ),
        None,
    )
    current_snapshot_matches = bool(
        project and analysis_record and analysis_record.premise_snapshot == project.premise
    )
    analysis = (
        _analysis_from_db(analysis_record)
        if current_snapshot_matches and analysis_record
        else None
    )
    if analysis is not None:
        analysis = _analysis_with_story_facts(db, project_id, analysis)
    story_facts = db.scalars(select(StoryFact).where(StoryFact.project_id == project_id)).all()
    try:
        extractions = []
        if current_snapshot_matches and analysis_record:
            stored_extractions = json.loads(analysis_record.extractions)
            extractions = (
                [PremiseMention.model_validate(item) for item in stored_extractions]
                if stored_extractions
                else parse_premise(project.premise)
            )
    except (ValidationError, json.JSONDecodeError, TypeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Saved premise extraction is invalid. Reanalyze the premise to restore it.",
        ) from error
    analysis_notice = None
    if current_snapshot_matches and analysis_record:
        analysis_notice = analysis_record.analysis_notice
        if analysis_record.analysis_mode == "deterministic":
            offline_notice = (
                "Deterministic offline mode shows literal premise extraction and unresolved fields only; "
                "it does not provide semantic narrative analysis."
            )
            analysis_notice = f"{analysis_notice} {offline_notice}" if analysis_notice else offline_notice
    return PremiseDevelopmentRead(
        analysis=analysis,
        conversation=[
            PremiseQuestionRead.model_validate(question)
            for question in questions
        ],
        current_question=(
            PremiseQuestionRead.model_validate(current)
            if current_snapshot_matches and current
            else None
        ),
        extractions=extractions,
        gaps=gap_records(analysis.narrative_elements) if analysis else [],
        foundation=assess_foundation(analysis.narrative_elements, extractions, story_facts) if analysis else [],
        analysis_mode=analysis_record.analysis_mode if current_snapshot_matches and analysis_record else None,
        analysis_notice=analysis_notice,
    )


def _record_story_fact_revision(db: Session, fact: StoryFact, action: str) -> None:
    db.add(StoryFactRevision(
        project_id=fact.project_id,
        fact_id=None if action == "deleted" else fact.id,
        action=action,
        category=fact.category,
        label=fact.label,
        original_value=fact.original_value or fact.value,
        value=fact.value,
        status=fact.status,
        source=fact.source,
        evidence=fact.evidence,
        source_text=fact.source_text,
        writer_confirmed=fact.writer_confirmed,
        intentionally_undecided=fact.intentionally_undecided,
    ))


def _decoded_list(value: str | None) -> list:
    try:
        decoded = json.loads(value or "[]")
        return decoded if isinstance(decoded, list) else []
    except json.JSONDecodeError:
        return []


def _entity_provenance(record: object) -> dict[str, object]:
    return {
        "source_type": getattr(record, "source_type"),
        "confirmation_status": getattr(record, "confirmation_status"),
        "evidence": getattr(record, "evidence"),
        "source_text": getattr(record, "source_text"),
        "source_refs": _decoded_list(getattr(record, "source_refs")),
        "created_at": getattr(record, "created_at"),
        "updated_at": getattr(record, "updated_at"),
    }


def _character_read(record: Character) -> CharacterRead:
    return CharacterRead.model_validate({
        **_entity_provenance(record),
        "id": record.id, "project_id": record.project_id, "name": record.name,
        "aliases": _decoded_list(record.aliases), "description": record.description,
        "role": record.role, "goals": record.goals, "motivations": record.motivations,
        "fears": record.fears, "strengths": record.strengths, "weaknesses": record.weaknesses,
        "character_arc": record.character_arc, "current_status": record.current_status,
        "status_effective_position": record.status_effective_position,
    })


def _relationship_read(record: StoryRelationship) -> RelationshipRead:
    return RelationshipRead.model_validate({
        **_entity_provenance(record), "id": record.id, "project_id": record.project_id,
        "character_a_id": record.character_a_id, "character_b_id": record.character_b_id,
        "character_a_name": record.character_a.name, "character_b_name": record.character_b.name,
        "relationship_type": record.relationship_type, "description": record.description,
    })


def _conflict_read(record: StoryConflict) -> ConflictRead:
    return ConflictRead.model_validate({
        **_entity_provenance(record), "id": record.id, "project_id": record.project_id,
        "description": record.description, "conflict_type": record.conflict_type,
        "status": record.status,
        "character_ids": [item.id for item in record.characters],
        "characters": [_character_read(item).model_dump() for item in record.characters],
        "objectives": _decoded_list(record.objectives), "stakes": record.stakes,
    })


def _location_read(record: Location) -> LocationRead:
    return LocationRead.model_validate({
        **_entity_provenance(record), "id": record.id, "project_id": record.project_id,
        "name": record.name, "description": record.description,
        "aliases": _decoded_list(record.aliases), "parent_location_id": record.parent_location_id,
        "parent_location_name": record.parent.name if record.parent else None,
        "characteristics": _decoded_list(record.characteristics),
    })


def _event_read(record: StoryEvent) -> StoryEventRead:
    return StoryEventRead.model_validate({
        **_entity_provenance(record), "id": record.id, "project_id": record.project_id,
        "description": record.description, "character_ids": [item.id for item in record.characters],
        "character_names": [item.name for item in record.characters], "location_id": record.location_id,
        "location_name": record.location.name if record.location else None,
        "timeline_position": record.timeline_position, "date_text": record.date_text,
        "related_event_ids": _decoded_list(record.related_event_ids),
        "dependency_event_ids": _decoded_list(record.dependency_event_ids),
    })


def _entity_snapshot(entity_type: str, record: object) -> dict[str, object]:
    readers = {
        "character": _character_read,
        "relationship": _relationship_read,
        "conflict": _conflict_read,
        "location": _location_read,
        "event": _event_read,
    }
    if entity_type not in readers:
        raise ValueError("Unknown Story Bible entity type.")
    return readers[entity_type](record).model_dump(mode="json")


def _record_entity_revision(
    db: Session, project_id: int, entity_type: str, record: object, action: str
) -> None:
    snapshot = _entity_snapshot(entity_type, record)
    db.add(StoryEntityRevision(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=getattr(record, "id", None),
        action=action,
        snapshot=json.dumps(snapshot, ensure_ascii=False),
    ))


def _project_characters(db: Session, project_id: int, ids: list[int]) -> list[Character]:
    unique_ids = list(dict.fromkeys(ids))
    records = db.scalars(select(Character).where(Character.project_id == project_id, Character.id.in_(unique_ids))).all() if unique_ids else []
    if len(records) != len(unique_ids):
        raise HTTPException(status_code=422, detail="Every linked character must belong to this project.")
    return records


def _project_location(db: Session, project_id: int, location_id: int | None) -> Location | None:
    if location_id is None:
        return None
    location = db.scalar(select(Location).where(Location.id == location_id, Location.project_id == project_id))
    if location is None:
        raise HTTPException(status_code=422, detail="The linked location must belong to this project.")
    return location


def _validate_event_links(db: Session, project_id: int, event_id: int | None, linked_ids: list[int]) -> None:
    ids = list(dict.fromkeys(linked_ids))
    if event_id is not None and event_id in ids:
        raise HTTPException(status_code=422, detail="An event cannot depend on or relate to itself.")
    records = db.scalars(select(StoryEvent).where(StoryEvent.project_id == project_id, StoryEvent.id.in_(ids))).all() if ids else []
    if len(records) != len(ids):
        raise HTTPException(status_code=422, detail="Every linked event must belong to this project.")


def _upsert_narrative_fact(
    db: Session,
    project_id: int,
    label: str,
    value: str,
    status: FactStatus,
    evidence: str,
    source_text: str,
    writer_confirmed: bool,
    intentionally_undecided: bool,
) -> None:
    fact = db.scalar(
        select(StoryFact).where(
            StoryFact.project_id == project_id,
            StoryFact.category == "Narrative element",
            StoryFact.label == label,
        )
    )
    if fact:
        _record_story_fact_revision(db, fact, "updated")
        fact.value = value
        fact.status = status
        fact.source = "Writer"
        fact.evidence = evidence
        fact.source_text = source_text
        fact.writer_confirmed = writer_confirmed
        fact.intentionally_undecided = intentionally_undecided
    else:
        fact = StoryFact(
            project_id=project_id,
            category="Narrative element",
            label=label,
            value=value,
            status=status,
            source="Writer",
            original_value=value,
            evidence=evidence,
            source_text=source_text,
            writer_confirmed=writer_confirmed,
            intentionally_undecided=intentionally_undecided,
        )
        db.add(fact)
        db.flush()
        _record_story_fact_revision(db, fact, "created")


_SKIP_RESPONSE = re.compile(
    r"^(?:(?:i(?:'d| would) like to|let's)\s+)?skip(?: this(?: question)?| this question)?"
    r"(?: for now| for the moment)?[.! ]*$",
    re.IGNORECASE,
)
_UNDECIDED_RESPONSE = re.compile(
    r"^(?:i\s+(?:haven't|have not)\s+decided(?:\s+(?:yet|on this))?"
    r"|i\s+(?:don't|do not)\s+want\s+to\s+decide(?:\s+this)?(?:\s+until\b.+)?"
    r"|i\s+(?:want|intend)\s+to\s+leave\s+(?:this|it)\s+undecided"
    r"|i\s+(?:intentionally\s+)?want\s+to\s+withhold\b.+)"
    r"[.! ]*$",
    re.IGNORECASE,
)


def _writer_response_status(response: str) -> str | None:
    if _SKIP_RESPONSE.fullmatch(response.strip()):
        return "skipped"
    if _UNDECIDED_RESPONSE.fullmatch(response.strip()):
        return "undecided"
    return None


def _preserve_writer_decisions(
    previous: PremiseAnalysis | None,
    analysis: PremiseAnalysisResult,
) -> None:
    if previous is None:
        return
    established = _analysis_from_db(previous)
    for key in NARRATIVE_LABELS:
        old_element = getattr(established.narrative_elements, key)
        if old_element.source == "writer":
            setattr(
                analysis.narrative_elements,
                key,
                old_element.model_copy(deep=True),
            )
    if established.narrative_elements.antagonist.source == "writer":
        analysis.antagonist_classification = established.antagonist_classification


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.scalars(select(Project).order_by(Project.updated_at.desc())).all()
    return [project_read(db, project.id) for project in projects]


@app.post("/api/projects", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    values = payload.model_dump(exclude={"setup_flow"})
    project = Project(
        **values,
        setup_step="questions" if payload.setup_flow else "complete",
    )
    act = Act(title="ACT I", order_index=0)
    scene = Scene(title="INT. LOCATION - DAY", order_index=0)
    scene.blocks = [ScreenplayBlock(type="action", text="", order_index=0)]
    act.scenes = [scene]
    project.acts = [act]
    db.add(project)
    db.commit()
    return project_read(db, project.id)


@app.get("/api/projects/{project_id}/setup", response_model=StorySetupRead)
def get_story_setup(project_id: int, db: Session = Depends(get_db)) -> StorySetupRead:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return StorySetupRead(
        step=project.setup_step,
        answers=json.loads(project.setup_answers or "{}"),
    )


@app.put("/api/projects/{project_id}/setup", response_model=StorySetupRead)
def update_story_setup(
    project_id: int,
    payload: StorySetupUpdate,
    db: Session = Depends(get_db),
) -> StorySetupRead:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    answers = {}
    for key, answer in payload.answers.items():
        value = answer.model_dump()
        if answer.status == "answered":
            decision = _writer_response_status(answer.response)
            if decision in {"skipped", "undecided"}:
                value["status"] = decision
        answers[key] = value
    project.setup_step = payload.step
    project.setup_answers = json.dumps(answers, ensure_ascii=False)
    db.commit()
    return StorySetupRead.model_validate({
        "step": project.setup_step,
        "answers": answers,
    })


@app.get("/api/preferences/tutorials", response_model=TutorialState)
def get_tutorial_state(db: Session = Depends(get_db)) -> TutorialState:
    preference = db.get(AppPreference, 1)
    if preference is None:
        return TutorialState()
    return TutorialState.model_validate_json(preference.tutorial_state)


@app.put("/api/preferences/tutorials", response_model=TutorialState)
def update_tutorial_state(
    payload: TutorialState,
    db: Session = Depends(get_db),
) -> TutorialState:
    preference = db.get(AppPreference, 1)
    if preference is None:
        preference = AppPreference(id=1)
        db.add(preference)
    preference.tutorial_state = payload.model_dump_json()
    db.commit()
    return payload


@app.patch("/api/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectRead:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    values = payload.model_dump(exclude_unset=True)
    premise_changed = "premise" in values and values["premise"] != project.premise
    for key, value in values.items():
        setattr(project, key, value)
    if premise_changed:
        for question in db.scalars(
            select(PremiseQuestion).where(
                PremiseQuestion.project_id == project_id,
                PremiseQuestion.status == "pending",
            )
        ).all():
            question.status = "superseded"
            question.response = "Archived because the writer changed the premise."
            question.answered_at = datetime.now(timezone.utc)
    db.commit()
    return project_read(db, project_id)


@app.post("/api/projects/{project_id}/acts", response_model=ProjectRead, status_code=201)
def create_act(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = get_project(db, project_id)
    order_index = len(project.acts)
    act = Act(project_id=project_id, order_index=order_index, title=f"ACT {order_index + 1}")
    act.scenes = [Scene(title="INT. LOCATION - DAY", order_index=0, blocks=[
        ScreenplayBlock(type="action", text="", order_index=0),
    ])]
    project.acts.append(act)
    db.commit()
    return project_read(db, project_id)


@app.post("/api/projects/{project_id}/acts/{act_id}/scenes", response_model=ProjectRead, status_code=201)
def create_scene(project_id: int, act_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    act = db.scalar(select(Act).where(Act.id == act_id, Act.project_id == project_id))
    if act is None:
        raise HTTPException(status_code=404, detail="Act not found in this project.")
    scene = Scene(
        title="INT. LOCATION - DAY",
        order_index=len(act.scenes),
        blocks=[ScreenplayBlock(type="action", text="", order_index=0)],
    )
    act.scenes.append(scene)
    db.commit()
    return project_read(db, project_id)


@app.put("/api/projects/{project_id}/scenes/{scene_id}", response_model=ProjectRead)
def update_scene(
    project_id: int,
    scene_id: int,
    payload: SceneUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    scene = get_scene(db, project_id, scene_id)
    values = payload.model_dump(exclude_unset=True, exclude={"blocks"})
    for key, value in values.items():
        setattr(scene, key, value)
    if payload.blocks is not None:
        reconcile_blocks(scene, payload.blocks)
    db.commit()
    return project_read(db, project_id)


@app.delete("/api/projects/{project_id}/scenes/{scene_id}", response_model=ProjectRead)
def delete_scene(project_id: int, scene_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    scene = get_scene(db, project_id, scene_id)
    scene.act.scenes.remove(scene)
    db.delete(scene)
    db.flush()
    renumber_scenes(db, project_id)
    db.commit()
    return project_read(db, project_id)


@app.post("/api/projects/{project_id}/scenes/{scene_id}/reorder", response_model=ProjectRead)
def reorder_scene(
    project_id: int,
    scene_id: int,
    payload: ReorderRequest,
    db: Session = Depends(get_db),
) -> ProjectRead:
    scene = get_scene(db, project_id, scene_id)
    source_act = scene.act
    if payload.direction is not None:
        siblings = list(source_act.scenes)
        index = next((i for i, item in enumerate(siblings) if item.id == scene_id), -1)
        target = index + (-1 if payload.direction == "up" else 1)
        if 0 <= index < len(siblings) and 0 <= target < len(siblings):
            siblings[index], siblings[target] = siblings[target], siblings[index]
            source_act.scenes = siblings
            for order_index, sibling in enumerate(siblings):
                sibling.order_index = order_index
    elif payload.target_scene_id is not None:
        target_scene = get_scene(db, project_id, payload.target_scene_id)
        target_act = target_scene.act
        target_scenes = list(target_act.scenes)
        target_index = next(i for i, item in enumerate(target_scenes) if item.id == target_scene.id)
        if target_scene.id != scene.id:
            source_act.scenes.remove(scene)
            target_scenes = [item for item in target_scenes if item.id != scene.id]
            target_index = next(i for i, item in enumerate(target_scenes) if item.id == target_scene.id)
            target_scenes.insert(target_index, scene)
            target_act.scenes = target_scenes
    elif payload.target_act_id is not None:
        target_act = db.scalar(
            select(Act).where(Act.id == payload.target_act_id, Act.project_id == project_id)
        )
        if target_act is None:
            raise HTTPException(status_code=404, detail="Target act not found in this project.")
        if target_act.id != source_act.id:
            source_act.scenes.remove(scene)
            target_act.scenes.append(scene)
    renumber_scenes(db, project_id)
    db.commit()
    return project_read(db, project_id)


_ENTITY_CONFIG = {
    "characters": (Character, CharacterInput, _character_read, "character"),
    "relationships": (StoryRelationship, RelationshipInput, _relationship_read, "relationship"),
    "conflicts": (StoryConflict, ConflictInput, _conflict_read, "conflict"),
    "locations": (Location, LocationInput, _location_read, "location"),
    "events": (StoryEvent, StoryEventInput, _event_read, "event"),
}


def _entity_payload_values(db: Session, project_id: int, kind: str, raw: dict) -> tuple[object, dict]:
    if kind not in _ENTITY_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown Story Bible entity collection.")
    model, schema, _, _ = _ENTITY_CONFIG[kind]
    try:
        payload = TypeAdapter(schema).validate_python(raw)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    values = payload.model_dump()
    values["source_refs"] = json.dumps(values["source_refs"], ensure_ascii=False)
    if kind == "characters":
        values["aliases"] = json.dumps(values["aliases"], ensure_ascii=False)
    elif kind == "relationships":
        _project_characters(db, project_id, [values["character_a_id"], values["character_b_id"]])
    elif kind == "conflicts":
        values["characters"] = _project_characters(db, project_id, values.pop("character_ids"))
        values["objectives"] = json.dumps(values["objectives"], ensure_ascii=False)
    elif kind == "locations":
        _project_location(db, project_id, values["parent_location_id"])
        values["aliases"] = json.dumps(values["aliases"], ensure_ascii=False)
        values["characteristics"] = json.dumps(values["characteristics"], ensure_ascii=False)
    elif kind == "events":
        values["characters"] = _project_characters(db, project_id, values.pop("character_ids"))
        _project_location(db, project_id, values["location_id"])
        linked = values["related_event_ids"] + values["dependency_event_ids"]
        _validate_event_links(db, project_id, None, linked)
        values["related_event_ids"] = json.dumps(values["related_event_ids"])
        values["dependency_event_ids"] = json.dumps(values["dependency_event_ids"])
    return payload, values


@app.get("/api/projects/{project_id}/story-bible/entities/{kind}")
def list_story_entities(project_id: int, kind: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if kind not in _ENTITY_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown Story Bible entity collection.")
    model, _, reader, _ = _ENTITY_CONFIG[kind]
    rows = db.scalars(select(model).where(model.project_id == project_id).order_by(model.id)).all()
    return [reader(row).model_dump(mode="json") for row in rows]


@app.post("/api/projects/{project_id}/story-bible/entities/{kind}", status_code=201)
def create_story_entity(project_id: int, kind: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    _, values = _entity_payload_values(db, project_id, kind, payload)
    model, _, reader, entity_type = _ENTITY_CONFIG[kind]
    record = model(project_id=project_id, **values)
    db.add(record)
    db.flush()
    _record_entity_revision(db, project_id, entity_type, record, "created")
    db.commit()
    db.refresh(record)
    return reader(record).model_dump(mode="json")


@app.put("/api/projects/{project_id}/story-bible/entities/{kind}/{entity_id}")
def update_story_entity(project_id: int, kind: str, entity_id: int, payload: dict, db: Session = Depends(get_db)) -> dict:
    if kind not in _ENTITY_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown Story Bible entity collection.")
    model, _, reader, entity_type = _ENTITY_CONFIG[kind]
    record = db.scalar(select(model).where(model.id == entity_id, model.project_id == project_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Story Bible entity not found.")
    _, values = _entity_payload_values(db, project_id, kind, payload)
    _record_entity_revision(db, project_id, entity_type, record, "updated")
    for key, value in values.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return reader(record).model_dump(mode="json")


@app.delete("/api/projects/{project_id}/story-bible/entities/{kind}/{entity_id}", status_code=204)
def delete_story_entity(project_id: int, kind: str, entity_id: int, db: Session = Depends(get_db)) -> Response:
    if kind not in _ENTITY_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown Story Bible entity collection.")
    model, _, _, entity_type = _ENTITY_CONFIG[kind]
    record = db.scalar(select(model).where(model.id == entity_id, model.project_id == project_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Story Bible entity not found.")
    _record_entity_revision(db, project_id, entity_type, record, "deleted")
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@app.post("/api/projects/{project_id}/story-bible/entities/characters/{entity_id}/merge")
def merge_story_character(project_id: int, entity_id: int, payload: EntityMergeRequest, db: Session = Depends(get_db)) -> dict:
    source = db.scalar(select(Character).where(Character.id == entity_id, Character.project_id == project_id))
    target = db.scalar(select(Character).where(Character.id == payload.target_id, Character.project_id == project_id))
    if source is None or target is None or source.id == target.id:
        raise HTTPException(status_code=404, detail="Choose two different characters in this project.")
    _record_entity_revision(db, project_id, "character", source, "merged")
    target.aliases = json.dumps(list(dict.fromkeys([*_decoded_list(target.aliases), source.name, *_decoded_list(source.aliases)])))
    target.conflicts = list({item.id: item for item in [*target.conflicts, *source.conflicts]}.values())
    target.events = list({item.id: item for item in [*target.events, *source.events]}.values())
    for relationship in [*source.as_character_a, *source.as_character_b]:
        if relationship.character_a_id == source.id:
            relationship.character_a_id = target.id
        if relationship.character_b_id == source.id:
            relationship.character_b_id = target.id
        if relationship.character_a_id == relationship.character_b_id:
            db.delete(relationship)
    db.delete(source)
    db.commit()
    db.refresh(target)
    return _character_read(target).model_dump(mode="json")


@app.get("/api/projects/{project_id}/story-bible/history", response_model=list[StoryEntityRevisionRead])
def list_entity_history(project_id: int, db: Session = Depends(get_db)) -> list[StoryEntityRevisionRead]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    rows = db.scalars(select(StoryEntityRevision).where(StoryEntityRevision.project_id == project_id).order_by(StoryEntityRevision.id.desc())).all()
    return [StoryEntityRevisionRead.model_validate({**row.__dict__, "snapshot": json.loads(row.snapshot)}) for row in rows]


@app.post("/api/projects/{project_id}/continuity/analyze", response_model=ContinuityAnalysisResult)
def analyze_continuity(project_id: int, db: Session = Depends(get_db)) -> ContinuityAnalysisResult:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    characters = db.scalars(select(Character).where(Character.project_id == project_id)).all()
    locations = db.scalars(select(Location).where(Location.project_id == project_id)).all()
    events = db.scalars(select(StoryEvent).where(StoryEvent.project_id == project_id).options(selectinload(StoryEvent.characters))).all()
    scenes = db.scalars(select(Scene).join(Act).where(Act.project_id == project_id).options(selectinload(Scene.blocks))).all()
    candidates = detect_continuity_candidates(project_id, characters, scenes, locations, events)
    current_fingerprints = {candidate["fingerprint"] for candidate in candidates}
    for candidate in candidates:
        finding = db.scalar(select(ContinuityFinding).where(ContinuityFinding.project_id == project_id, ContinuityFinding.fingerprint == candidate["fingerprint"]))
        encoded = {key: json.dumps(candidate[key], ensure_ascii=False) for key in ("relevant_character_ids", "relevant_scene_ids", "evidence_refs")}
        if finding is None:
            db.add(ContinuityFinding(project_id=project_id, **{**candidate, **encoded}))
        else:
            finding.description = candidate["description"]
            finding.resolution_status = "resolved" if finding.disposition in {"dismissed", "explained", "accepted_intentional"} else "open"
            finding.detected_at = datetime.now(timezone.utc)
    for old in db.scalars(select(ContinuityFinding).where(ContinuityFinding.project_id == project_id, ContinuityFinding.resolution_status == "open")).all():
        if old.fingerprint not in current_fingerprints:
            old.resolution_status = "resolved"
    db.commit()
    rows = db.scalars(select(ContinuityFinding).where(ContinuityFinding.project_id == project_id).order_by(ContinuityFinding.detected_at.desc())).all()
    return ContinuityAnalysisResult(findings=[_finding_read(row) for row in rows], analyzed_scenes=sum(scene.completed for scene in scenes), message=f"Checked {sum(scene.completed for scene in scenes)} completed scene(s) and confirmed timeline events.")


def _finding_read(row: ContinuityFinding) -> ContinuityFindingRead:
    return ContinuityFindingRead.model_validate({
        "id": row.id, "finding_type": row.finding_type, "description": row.description,
        "severity": row.severity, "confidence": row.confidence,
        "relevant_character_ids": _decoded_list(row.relevant_character_ids),
        "relevant_scene_ids": _decoded_list(row.relevant_scene_ids),
        "evidence_refs": _decoded_list(row.evidence_refs), "disposition": row.disposition,
        "writer_explanation": row.writer_explanation, "resolution_status": row.resolution_status,
        "detected_at": row.detected_at,
    })


@app.get("/api/projects/{project_id}/continuity/findings", response_model=list[ContinuityFindingRead])
def list_continuity_findings(project_id: int, db: Session = Depends(get_db)) -> list[ContinuityFindingRead]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    rows = db.scalars(select(ContinuityFinding).where(ContinuityFinding.project_id == project_id).order_by(ContinuityFinding.detected_at.desc())).all()
    return [_finding_read(row) for row in rows]


@app.put("/api/projects/{project_id}/continuity/findings/{finding_id}", response_model=ContinuityFindingRead)
def update_continuity_finding(project_id: int, finding_id: int, payload: ContinuityDispositionUpdate, db: Session = Depends(get_db)) -> ContinuityFindingRead:
    row = db.scalar(select(ContinuityFinding).where(ContinuityFinding.project_id == project_id, ContinuityFinding.id == finding_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Continuity finding not found.")
    if payload.disposition == "explained" and not payload.writer_explanation.strip():
        raise HTTPException(status_code=422, detail="Add an explanation before marking this finding explained.")
    row.disposition = payload.disposition
    row.writer_explanation = payload.writer_explanation
    row.resolution_status = "open" if payload.disposition in {"unreviewed", "needs_correction"} else "resolved"
    db.commit()
    db.refresh(row)
    return _finding_read(row)


@app.get("/api/projects/{project_id}/facts", response_model=list[StoryFactRead])
def list_facts(project_id: int, db: Session = Depends(get_db)) -> list[StoryFactRead]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    facts = db.scalars(select(StoryFact).where(StoryFact.project_id == project_id).order_by(StoryFact.id)).all()
    return [StoryFactRead.model_validate(fact) for fact in facts]


@app.get(
    "/api/projects/{project_id}/facts/history",
    response_model=list[StoryFactRevisionRead],
)
def list_fact_history(project_id: int, db: Session = Depends(get_db)) -> list[StoryFactRevisionRead]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    revisions = db.scalars(
        select(StoryFactRevision)
        .where(StoryFactRevision.project_id == project_id)
        .order_by(StoryFactRevision.id.desc())
    ).all()
    return [StoryFactRevisionRead.model_validate(revision) for revision in revisions]


@app.post("/api/projects/{project_id}/facts", response_model=StoryFactRead, status_code=201)
def create_fact(
    project_id: int,
    payload: StoryFactCreate,
    db: Session = Depends(get_db),
) -> StoryFactRead:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    values = payload.model_dump()
    values["writer_confirmed"] = values["writer_confirmed"] and values["status"] == "confirmed"
    fact = StoryFact(
        project_id=project_id,
        original_value=values["value"],
        **values,
    )
    db.add(fact)
    db.flush()
    _record_story_fact_revision(db, fact, "created")
    db.commit()
    db.refresh(fact)
    return StoryFactRead.model_validate(fact)


@app.put("/api/projects/{project_id}/facts/{fact_id}", response_model=StoryFactRead)
def update_fact(
    project_id: int,
    fact_id: int,
    payload: StoryFactUpdate,
    db: Session = Depends(get_db),
) -> StoryFactRead:
    fact = db.scalar(
        select(StoryFact).where(StoryFact.id == fact_id, StoryFact.project_id == project_id)
    )
    if fact is None:
        raise HTTPException(status_code=404, detail="Story Bible fact not found.")
    _record_story_fact_revision(db, fact, "updated")
    values = payload.model_dump()
    for key, value in values.items():
        setattr(fact, key, value)
    fact.writer_confirmed = fact.writer_confirmed and fact.status == "confirmed"
    db.commit()
    db.refresh(fact)
    return StoryFactRead.model_validate(fact)


@app.delete("/api/projects/{project_id}/facts/{fact_id}", status_code=204)
def delete_fact(project_id: int, fact_id: int, db: Session = Depends(get_db)) -> Response:
    fact = db.scalar(select(StoryFact).where(StoryFact.id == fact_id, StoryFact.project_id == project_id))
    if fact is None:
        raise HTTPException(status_code=404, detail="Story Bible fact not found.")
    _record_story_fact_revision(db, fact, "deleted")
    db.delete(fact)
    db.commit()
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/development", response_model=PremiseDevelopmentRead)
def get_development(project_id: int, db: Session = Depends(get_db)) -> PremiseDevelopmentRead:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return _development_state(db, project_id)


@app.post("/api/projects/{project_id}/development/analyze", response_model=PremiseDevelopmentRead)
def analyze_premise(project_id: int, db: Session = Depends(get_db)) -> PremiseDevelopmentRead:
    project = get_project(db, project_id)
    if not project.premise.strip():
        raise HTTPException(status_code=400, detail="Add a premise before analyzing the story.")

    premise_snapshot = project.premise
    existing = db.scalar(select(PremiseAnalysis).where(PremiseAnalysis.project_id == project_id))
    if existing and existing.premise_snapshot == premise_snapshot:
        return _development_state(db, project_id)

    extractions = parse_premise(premise_snapshot)
    messages = [
        {"role": "system", "content": PREMISE_ANALYSIS_PROMPT},
        {
            "role": "user",
            "content": json.dumps({
                "premise": premise_snapshot,
                "literal_premise_extractions": [
                    item.model_dump() for item in extractions
                ],
                "required_statuses": ["EXPLICIT", "INFERRED", "UNDECIDED", "NOT_APPLICABLE"],
            }, ensure_ascii=False),
        },
    ]
    db.rollback()
    analysis_mode = "ai"
    analysis_notice = None
    try:
        raw_result = _ai_provider().generate_json(messages, PremiseAnalysisResult.model_json_schema())
        raw_result["premise"] = premise_snapshot
        analysis = PremiseAnalysisResult.model_validate(raw_result)
        analysis = _ground_analysis_to_premise(analysis)
    except OllamaInvalidResponse as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        analysis = deterministic_analysis(premise_snapshot, extractions)
        analysis_mode = "deterministic"
        analysis_notice = str(error)
    except ValidationError as error:
        raise HTTPException(
            status_code=502,
            detail=f"The model returned an incomplete premise analysis: {error.error_count()} validation error(s).",
        ) from error

    _preserve_writer_decisions(existing, analysis)
    db.refresh(project, attribute_names=["premise"])
    if project.premise != premise_snapshot:
        raise HTTPException(
            status_code=409,
            detail="The premise changed while analysis was running. The saved premise was kept; retry analysis.",
        )
    for old_question in db.scalars(
        select(PremiseQuestion).where(
            PremiseQuestion.project_id == project_id,
            PremiseQuestion.premise_snapshot != premise_snapshot,
            PremiseQuestion.status == "pending",
        )
    ).all():
        old_question.status = "superseded"
        old_question.response = "Archived because the writer changed the premise."
        old_question.answered_at = datetime.now(timezone.utc)
    if project.genre.strip():
        analysis.narrative_elements.genre = NarrativeElement(
            value=project.genre.strip(),
            status="EXPLICIT",
            evidence="Provided by the writer in project details.",
            source="writer",
        )
    serialized = analysis.model_dump_json()
    if existing:
        existing.premise_snapshot = project.premise
        existing.narrative_elements = serialized
        existing.extractions = json.dumps(
            [item.model_dump() for item in extractions],
            ensure_ascii=False,
        )
        existing.analysis_mode = analysis_mode
        existing.analysis_notice = analysis_notice
        existing.analyzed_at = datetime.now(timezone.utc)
    else:
        db.add(PremiseAnalysis(
            project_id=project_id,
            premise_snapshot=project.premise,
            narrative_elements=serialized,
            extractions=json.dumps(
                [item.model_dump() for item in extractions],
                ensure_ascii=False,
            ),
            analysis_mode=analysis_mode,
            analysis_notice=analysis_notice,
        ))
    try:
        db.commit()
    except IntegrityError:
        # A second analysis request may finish the same premise while this request
        # is generating its result. Reuse that committed row instead of returning 500.
        db.rollback()
        concurrent = db.scalar(select(PremiseAnalysis).where(PremiseAnalysis.project_id == project_id))
        if concurrent is None or concurrent.premise_snapshot != premise_snapshot:
            raise
    return _development_state(db, project_id)


@app.post("/api/projects/{project_id}/development/next-question", response_model=PremiseDevelopmentRead)
def create_next_premise_question(project_id: int, db: Session = Depends(get_db)) -> PremiseDevelopmentRead:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    analysis_record = db.scalar(select(PremiseAnalysis).where(PremiseAnalysis.project_id == project_id))
    if analysis_record is None or analysis_record.premise_snapshot != project.premise:
        raise HTTPException(status_code=409, detail="Analyze the current premise before generating a question.")

    questions = db.scalars(
        select(PremiseQuestion).where(
            PremiseQuestion.project_id == project_id,
            PremiseQuestion.premise_snapshot == project.premise,
        )
    ).all()
    setup_answers = json.loads(project.setup_answers or "{}")
    setup_context = [
        {
            "element_key": SETUP_QUESTION_ELEMENTS[question_id],
            "question": question_id,
            "status": answer["status"],
            "writer_response": answer.get("response", "")[:600],
        }
        for question_id, answer in setup_answers.items()
        if question_id in SETUP_QUESTION_ELEMENTS and answer.get("status") in {
            "answered", "skipped", "undecided",
        }
    ]
    setup_covered_keys = {item["element_key"] for item in setup_context}
    analysis = _analysis_with_story_facts(db, project_id, _analysis_from_db(analysis_record))
    pending = next((question for question in questions if question.status == "pending"), None)
    if pending:
        element = getattr(analysis.narrative_elements, pending.element_key)
        already_established = element.status in {"EXPLICIT", "NOT_APPLICABLE"} or (
            element.source == "writer" and element.intentionally_undecided
        )
        if pending.element_key not in setup_covered_keys and not already_established:
            return _development_state(db, project_id)
        pending.status = "superseded"
        pending.response = (
            "Covered by a response or decision in guided Story Setup."
            if pending.element_key in setup_covered_keys
            else "Covered by established or intentionally deferred Story Bible information."
        )
        pending.answered_at = datetime.now(timezone.utc)
        db.flush()

    asked_keys = {question.element_key for question in questions} | setup_covered_keys
    selected_gap = next_gap(analysis.narrative_elements, asked_keys)
    if selected_gap is None:
        db.commit()
        return _development_state(db, project_id)

    premise_snapshot = project.premise
    suggestion = offline_question(selected_gap)
    db.refresh(project, attribute_names=["premise"])
    if project.premise != premise_snapshot:
        raise HTTPException(
            status_code=409,
            detail="The premise changed while the question was being generated. Retry with the current premise.",
        )
    db.add(PremiseQuestion(
        project_id=project_id,
        element_key=selected_gap,
        question=suggestion.question.strip(),
        premise_snapshot=premise_snapshot,
        status="pending",
    ))
    db.commit()
    return _development_state(db, project_id)


@app.post(
    "/api/projects/{project_id}/development/questions/{question_id}",
    response_model=PremiseDevelopmentRead,
)
def answer_premise_question(
    project_id: int,
    question_id: int,
    payload: PremiseAnswerRequest,
    db: Session = Depends(get_db),
) -> PremiseDevelopmentRead:
    question = db.scalar(
        select(PremiseQuestion).where(
            PremiseQuestion.id == question_id,
            PremiseQuestion.project_id == project_id,
        )
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Premise question not found.")
    if question.status != "pending":
        raise HTTPException(status_code=409, detail="This question has already been resolved.")
    project = db.get(Project, project_id)
    if project is None or question.premise_snapshot != project.premise:
        raise HTTPException(
            status_code=409,
            detail="This question belongs to an earlier premise version. Analyze the current premise first.",
        )
    if payload.status == "answered" and not payload.response.strip():
        raise HTTPException(status_code=422, detail="Enter an answer, or skip/mark the question undecided.")

    analysis_record = db.scalar(select(PremiseAnalysis).where(PremiseAnalysis.project_id == project_id))
    if analysis_record is None:
        raise HTTPException(status_code=409, detail="Premise analysis is unavailable.")
    analysis = _analysis_from_db(analysis_record)
    element = getattr(analysis.narrative_elements, question.element_key)
    writer_response = payload.response.strip()
    response_status = (
        _writer_response_status(writer_response)
        if payload.status == "answered"
        else None
    )
    question_status = response_status or payload.status
    question.status = question_status
    question.response = writer_response
    question.answered_at = datetime.now(timezone.utc)

    if question_status == "answered":
        element.value = writer_response
        element.status = "EXPLICIT"
        element.source = "writer"
        element.evidence = f"Confirmed by the writer in response to: {question.question}"
        element.confidence = 1.0
        element.explanation = "The writer explicitly confirmed this information."
        element.writer_confirmed = True
        element.intentionally_undecided = False
        label = NARRATIVE_LABELS[question.element_key]
        _upsert_narrative_fact(
            db,
            project_id,
            label,
            writer_response,
            "confirmed",
            element.evidence,
            question.question,
            True,
            False,
        )
        if question.element_key == "antagonist":
            analysis.antagonist_classification = "explicit_antagonist"
    elif question_status in {"undecided", "not_applicable"}:
        element.value = None
        element.status = "UNDECIDED" if question_status == "undecided" else "NOT_APPLICABLE"
        element.source = "writer"
        if question_status == "undecided":
            element.evidence = (
                f"The writer chose to leave this element undecided: {writer_response}"[:1_000]
                if writer_response
                else "The writer chose to leave this element undecided."
            )
            element.explanation = (
                f"Writer's decision: {writer_response}"[:1_000]
                if writer_response
                else "The writer intentionally left this element undecided."
            )
        else:
            element.evidence = "The writer established that this element is not applicable."
            element.explanation = "The writer confirmed that this element does not apply."
        element.confidence = 0.0 if question_status == "undecided" else 1.0
        element.writer_confirmed = question_status == "not_applicable"
        element.intentionally_undecided = question_status == "undecided"
        label = NARRATIVE_LABELS[question.element_key]
        if question_status == "undecided":
            decision_text = writer_response or "Intentionally left undecided by the writer."
            _upsert_narrative_fact(
                db,
                project_id,
                label,
                decision_text,
                "undecided",
                element.evidence,
                question.question,
                False,
                True,
            )
        else:
            fact = db.scalar(
                select(StoryFact).where(
                    StoryFact.project_id == project_id,
                    StoryFact.category == "Narrative element",
                    StoryFact.label == label,
                )
            )
            if fact:
                _record_story_fact_revision(db, fact, "deleted")
                db.delete(fact)
        if question.element_key == "antagonist":
            analysis.antagonist_classification = (
                "no_conventional_antagonist"
                if question_status == "not_applicable"
                else "undecided"
            )

    analysis_record.narrative_elements = analysis.model_dump_json()
    db.commit()
    return _development_state(db, project_id)


@app.post(
    "/api/projects/{project_id}/development/questions/{question_id}/reopen",
    response_model=PremiseDevelopmentRead,
)
def reopen_premise_question(
    project_id: int,
    question_id: int,
    db: Session = Depends(get_db),
) -> PremiseDevelopmentRead:
    question = db.scalar(
        select(PremiseQuestion).where(
            PremiseQuestion.id == question_id,
            PremiseQuestion.project_id == project_id,
        )
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Premise question not found.")
    project = db.get(Project, project_id)
    if project is None or question.premise_snapshot != project.premise:
        raise HTTPException(
            status_code=409,
            detail="This question belongs to an earlier premise version and cannot be reopened.",
        )
    if question.status not in {"skipped", "undecided", "not_applicable"}:
        raise HTTPException(status_code=409, detail="Only skipped or undecided questions can be reopened.")
    pending = db.scalar(
        select(PremiseQuestion).where(
            PremiseQuestion.project_id == project_id,
            PremiseQuestion.status == "pending",
        )
    )
    if pending:
        raise HTTPException(status_code=409, detail="Resolve or skip the current question before reopening another.")
    db.add(PremiseQuestion(
        project_id=project_id,
        element_key=question.element_key,
        question=question.question,
        premise_snapshot=question.premise_snapshot,
        status="pending",
    ))
    db.commit()
    return _development_state(db, project_id)


@app.put(
    "/api/projects/{project_id}/development/elements/{element_key}",
    response_model=PremiseDevelopmentRead,
)
def update_premise_element(
    project_id: int,
    element_key: str,
    payload: PremiseElementUpdate,
    db: Session = Depends(get_db),
) -> PremiseDevelopmentRead:
    if element_key not in NARRATIVE_LABELS:
        raise HTTPException(status_code=404, detail="Narrative element not found.")
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    record = db.scalar(select(PremiseAnalysis).where(PremiseAnalysis.project_id == project_id))
    if record is None or record.premise_snapshot != project.premise:
        raise HTTPException(status_code=409, detail="Analyze the current premise before editing its elements.")

    analysis = _analysis_from_db(record)
    element = getattr(analysis.narrative_elements, element_key)
    element.status = payload.status
    element.value = payload.value.strip() if payload.value else None
    element.source = "writer"
    element.evidence = "Edited or confirmed by the writer in the Story Bible."
    element.confidence = {
        "EXPLICIT": 1.0,
        "INFERRED": 0.5,
        "UNDECIDED": 0.0,
        "NOT_APPLICABLE": 1.0,
    }[payload.status]
    element.explanation = (
        "The writer directly confirmed this information."
        if payload.status == "EXPLICIT"
        else "The writer recorded this as an interpretation."
        if payload.status == "INFERRED"
        else "The writer intentionally left this element undecided."
        if payload.status == "UNDECIDED"
        else "The writer established that this element does not apply."
    )
    element.writer_confirmed = payload.status in {"EXPLICIT", "NOT_APPLICABLE"}
    element.intentionally_undecided = payload.status == "UNDECIDED"
    if element_key == "antagonist":
        if payload.status == "EXPLICIT":
            analysis.antagonist_classification = "explicit_antagonist"
        elif payload.status == "INFERRED":
            analysis.antagonist_classification = (
                "antagonistic_force"
                if "force" in (element.value or "").lower()
                else "potential_antagonist"
            )
        elif payload.status == "NOT_APPLICABLE":
            analysis.antagonist_classification = "no_conventional_antagonist"
        else:
            analysis.antagonist_classification = "undecided"

    label = NARRATIVE_LABELS[element_key]
    fact = db.scalar(
        select(StoryFact).where(
            StoryFact.project_id == project_id,
            StoryFact.category == "Narrative element",
            StoryFact.label == label,
        )
    )
    if payload.status in {"EXPLICIT", "INFERRED"}:
        fact_status = "confirmed" if payload.status == "EXPLICIT" else "inferred"
        if fact:
            _record_story_fact_revision(db, fact, "updated")
            fact.value = element.value or ""
            fact.status = fact_status
            fact.source = "Writer"
            fact.evidence = element.evidence
            fact.source_text = element.evidence
            fact.writer_confirmed = payload.status == "EXPLICIT"
            fact.intentionally_undecided = False
        else:
            fact = StoryFact(
                project_id=project_id,
                category="Narrative element",
                label=label,
                value=element.value or "",
                status=fact_status,
                source="Writer",
                original_value=element.value or "",
                evidence=element.evidence,
                source_text=element.evidence,
                writer_confirmed=payload.status == "EXPLICIT",
            )
            db.add(fact)
            db.flush()
            _record_story_fact_revision(db, fact, "created")
    elif fact:
        _record_story_fact_revision(db, fact, "deleted")
        db.delete(fact)

    pending = db.scalar(
        select(PremiseQuestion).where(
            PremiseQuestion.project_id == project_id,
            PremiseQuestion.element_key == element_key,
            PremiseQuestion.status == "pending",
        )
    )
    if pending and payload.status != "INFERRED":
        pending.status = {
            "EXPLICIT": "answered",
            "UNDECIDED": "undecided",
            "NOT_APPLICABLE": "not_applicable",
        }[payload.status]
        pending.response = element.value or "Updated by the writer in the Story Bible."
        pending.answered_at = datetime.now(timezone.utc)

    record.narrative_elements = analysis.model_dump_json()
    db.commit()
    return _development_state(db, project_id)


def request_ollama(messages: list[dict[str, str]], model: str, num_gpu: int) -> str:
    base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"response": {"type": "string"}},
        "required": ["response"],
    }
    payload = _ollama_payload(
        messages,
        model,
        num_predict=400,
        num_gpu=num_gpu,
        response_schema=schema,
    )
    content_parts: list[str] = []
    received_data = False
    try:
        context_length = int(os.environ.get("OLLAMA_NUM_CTX", "6144"))
    except ValueError as error:
        raise RuntimeError("OLLAMA_NUM_CTX must be a valid integer.") from error
    model_loaded = False
    try:
        with httpx.Client(timeout=_ollama_timeout()) as client:
            model_loaded = _ollama_model_loaded(client, base_url, model, context_length)
            with client.stream("POST", f"{base_url}/api/chat", json=payload) as response:
                if response.is_error:
                    raise _ollama_error(response.status_code, response.read().decode("utf-8", errors="replace"), model)
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise OllamaInvalidResponse("Ollama returned an invalid streaming response.") from error
                    received_data = True
                    if isinstance(item, dict) and isinstance(item.get("error"), str):
                        message = item["error"]
                        if "not found" in message.lower() and "model" in message.lower():
                            raise _ollama_error(404, message, model)
                        raise RuntimeError(f"Ollama reported an error: {message}")
                    message = item.get("message") if isinstance(item, dict) else None
                    chunk = message.get("content") if isinstance(message, dict) else None
                    if isinstance(chunk, str):
                        content_parts.append(chunk)
    except (httpx.HTTPError, OSError) as error:
        raise _raise_ollama_transport_error(
            error, base_url, model, received_data, model_loaded
        ) from error
    try:
        parsed = json.loads("".join(content_parts))
    except json.JSONDecodeError as error:
        raise OllamaInvalidResponse(
            "The selected model did not return valid JSON. Try again or select another model."
        ) from error
    answer = parsed.get("response") if isinstance(parsed, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise OllamaInvalidResponse("The selected model returned an empty or invalid response.")
    return answer.strip()


async def _ollama_assistant_stream(messages: list[dict[str, str]], model: str, num_gpu: int):
    base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    payload = _ollama_payload(messages, model, num_predict=400, num_gpu=num_gpu)
    received_data = False
    done_reason: str | None = None
    try:
        context_length = int(os.environ.get("OLLAMA_NUM_CTX", "6144"))
    except ValueError as error:
        raise RuntimeError("OLLAMA_NUM_CTX must be a valid integer.") from error
    model_loaded = False
    try:
        async with httpx.AsyncClient(timeout=_ollama_timeout()) as client:
            model_loaded = await _ollama_model_loaded_async(client, base_url, model, context_length)
            async with client.stream("POST", f"{base_url}/api/chat", json=payload) as response:
                if response.is_error:
                    details = (await response.aread()).decode("utf-8", errors="replace")
                    raise _ollama_error(response.status_code, details, model)
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise OllamaInvalidResponse("Ollama returned an invalid streaming response.") from error
                    received_data = True
                    if isinstance(item, dict) and isinstance(item.get("error"), str):
                        message = item["error"]
                        if "not found" in message.lower() and "model" in message.lower():
                            raise _ollama_error(404, message, model)
                        raise RuntimeError(f"Ollama reported an error: {message}")
                    message = item.get("message") if isinstance(item, dict) else None
                    chunk = message.get("content") if isinstance(message, dict) else None
                    if isinstance(chunk, str) and chunk:
                        yield {"type": "token", "content": chunk}
                        await asyncio.sleep(0)
                    if isinstance(item, dict) and item.get("done") is True:
                        reason = item.get("done_reason")
                        done_reason = reason if isinstance(reason, str) else None
        if done_reason == "length":
            raise OllamaInvalidResponse(
                "Ollama reached its response limit before finishing. Increase the output limit or retry."
            )
    except (httpx.HTTPError, OSError) as error:
        raise _raise_ollama_transport_error(
            error, base_url, model, received_data, model_loaded
        ) from error


def _ai_provider() -> OllamaProvider:
    return OllamaProvider(_ollama_json, _ollama_assistant_stream)


def _assistant_messages(
    project: Project,
    confirmed_facts: list[StoryFact],
    selected_scene: Scene | None,
    prompt: str,
) -> list[dict[str, str]]:
    context: dict[str, object] = {
        "project": {
            "title": project.title,
            "format": project.format,
            "genre": project.genre,
            "premise": project.premise,
        },
        "writer_confirmed_facts": [{"label": fact.label, "value": fact.value} for fact in confirmed_facts],
    }
    if selected_scene:
        context["scene"] = {
            "heading": selected_scene.title,
            "description": selected_scene.description,
            "action_and_visual_blocks": [
                block.text for block in selected_scene.blocks
                if block.type in {"action", "scene_heading", "shot", "transition"}
            ],
        }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Context (unconfirmed information is omitted): {json.dumps(context, ensure_ascii=False)}\n\n"
                f"Writer's request: {prompt}\n\n"
                "Do not fill gaps with invented story facts. If the writer requests dialogue or dialogue analysis, decline."
            ),
        },
    ]


def _sse(event: dict[str, str]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/api/projects/{project_id}/assistant/stream")
async def ask_assistant_stream(
    project_id: int,
    payload: AssistantRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    project = get_project(db, project_id)
    selected_scene = get_scene(db, project_id, payload.scene_id) if payload.scene_id is not None else None
    dialogue_request = re.search(
        r"\b(dialogue|dialog|lines for|write (?:a )?conversation|what should .{1,40} say)\b",
        payload.prompt,
        flags=re.IGNORECASE,
    )
    if dialogue_request:
        async def decline():
            yield _sse({
                "type": "token",
                "content": (
                    "I can't write or analyze dialogue. I can help with the scene's established "
                    "context, structure, or non-dialogue visual elements."
                ),
            })
            yield _sse({"type": "done", "model": "Sorkins boundary policy"})
        return StreamingResponse(decline(), media_type="text/event-stream")

    confirmed_facts = db.scalars(
        select(StoryFact).where(
            StoryFact.project_id == project_id,
            StoryFact.status == "confirmed",
            StoryFact.writer_confirmed.is_(True),
        )
    ).all()
    model = os.environ.get("OLLAMA_MODEL", "qwen3-vl:4b")
    try:
        configured_gpu_layers = max(0, int(os.environ.get("OLLAMA_NUM_GPU", "0")))
    except ValueError as error:
        raise HTTPException(status_code=500, detail="OLLAMA_NUM_GPU must be a valid integer.") from error
    messages = _assistant_messages(project, confirmed_facts, selected_scene, payload.prompt)

    async def events():
        streamed_any = False
        try:
            async for event in _ai_provider().stream_text(messages, model, configured_gpu_layers):
                streamed_any = True
                yield _sse(event)
            yield _sse({"type": "done", "model": model})
        except OllamaInvalidResponse as error:
            yield _sse({"type": "error", "message": str(error)})
        except RuntimeError as error:
            if not streamed_any and configured_gpu_layers > 0 and any(
                phrase in str(error).lower()
                for phrase in ("out of memory", "cuda allocation", "failed to allocate")
            ):
                try:
                    async for event in _ai_provider().stream_text(messages, model, 0):
                        yield _sse(event)
                    yield _sse({"type": "done", "model": model})
                    return
                except RuntimeError as retry_error:
                    yield _sse({"type": "error", "message": str(retry_error)})
                    return
            yield _sse({"type": "error", "message": str(error)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/projects/{project_id}/assistant", response_model=AssistantResponse)
def ask_assistant(
    project_id: int,
    payload: AssistantRequest,
    db: Session = Depends(get_db),
) -> AssistantResponse:
    project = get_project(db, project_id)
    selected_scene = None
    if payload.scene_id is not None:
        selected_scene = get_scene(db, project_id, payload.scene_id)

    dialogue_request = re.search(
        r"\b(dialogue|dialog|lines for|write (?:a )?conversation|what should .{1,40} say)\b",
        payload.prompt,
        flags=re.IGNORECASE,
    )
    if dialogue_request:
        return AssistantResponse(
            response="I can't write or analyze dialogue. I can help with the scene's established context, structure, or non-dialogue visual elements.",
            model="Sorkins boundary policy",
        )

    confirmed_facts = db.scalars(
        select(StoryFact).where(
            StoryFact.project_id == project_id,
            StoryFact.status == "confirmed",
        )
    ).all()
    model = os.environ.get("OLLAMA_MODEL", "qwen3-vl:4b")
    try:
        configured_gpu_layers = max(0, int(os.environ.get("OLLAMA_NUM_GPU", "0")))
    except ValueError as error:
        raise HTTPException(status_code=500, detail="OLLAMA_NUM_GPU must be a valid integer.") from error
    messages = _assistant_messages(project, confirmed_facts, selected_scene, payload.prompt)
    try:
        try:
            answer = request_ollama(messages, model, configured_gpu_layers)
        except RuntimeError as error:
            if configured_gpu_layers == 0 or not any(
                phrase in str(error).lower()
                for phrase in ("out of memory", "cuda allocation", "failed to allocate")
            ):
                raise
            answer = request_ollama(messages, model, 0)
    except OllamaInvalidResponse as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return AssistantResponse(response=answer, model=model)
