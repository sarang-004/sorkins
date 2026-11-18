import hashlib
import json
import re
from collections import defaultdict
from typing import Any


_EXEMPT_CONTEXTS = {"flashback", "dream", "alternate", "unreliable"}


def _fingerprint(project_id: int, kind: str, evidence: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        {"project_id": project_id, "kind": kind, "evidence": evidence},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _character_cues(scene: Any) -> dict[str, str]:
    cues: dict[str, str] = {}
    for block in scene.blocks:
        if block.type != "character":
            continue
        cue = re.sub(r"\s+\([^)]*\)\s*$", "", block.text).strip(" \t\r\n:.").casefold()
        if cue:
            cues[cue] = block.text.strip()
    return cues


def _scene_location(scene: Any, locations: list[Any]) -> Any | None:
    match = re.match(r"^\s*(?:INT\.?|EXT\.?|I/E)\s+(.+?)\s+-\s*(?:DAY|NIGHT|DAWN|DUSK|LATER|CONTINUOUS)\b", scene.title, re.I)
    if not match:
        return None
    heading_name = re.sub(r"\s+", " ", match.group(1)).strip().casefold()
    for location in locations:
        names = [location.name, *json.loads(location.aliases or "[]")]
        if any(heading_name == re.sub(r"\s+", " ", name).strip().casefold() for name in names):
            return location
    return None


def detect_continuity_candidates(
    project_id: int,
    characters: list[Any],
    scenes: list[Any],
    locations: list[Any],
    story_events: list[Any],
) -> list[dict[str, Any]]:
    """Return narrowly scoped findings supported by writer-confirmed, comparable sources."""
    candidates: list[dict[str, Any]] = []
    completed = [scene for scene in scenes if scene.completed and scene.timeline_position is not None]

    for character in characters:
        if (
            character.current_status.casefold() not in {"dead", "deceased"}
            or character.status_effective_position is None
            or character.confirmation_status != "writer_confirmed"
        ):
            continue
        aliases = {character.name.casefold(), *[alias.casefold() for alias in json.loads(character.aliases or "[]")]}
        for scene in completed:
            if scene.timeline_position <= character.status_effective_position or scene.timeline_context in _EXEMPT_CONTEXTS:
                continue
            cues = _character_cues(scene)
            cue = next((cues[name] for name in aliases if name in cues), None)
            if cue is None:
                continue
            evidence = [
                {
                    "kind": "character_status", "id": character.id, "label": character.name,
                    "text": character.evidence or f"Current status: {character.current_status}",
                    "source_type": character.source_type,
                    "timeline_position": character.status_effective_position,
                },
                {
                    "kind": "scene_character_cue", "id": scene.id, "label": scene.title,
                    "text": cue, "timeline_position": scene.timeline_position,
                    "timeline_context": scene.timeline_context,
                },
            ]
            candidates.append({
                "fingerprint": _fingerprint(project_id, "dead_character_appearance", evidence),
                "finding_type": "character_status",
                "description": (
                    f"{character.name} is recorded as dead by timeline position "
                    f"{character.status_effective_position}, but appears as a character cue in a later scene. "
                    "Review whether this scene is in the present timeline or needs an explicit exception."
                ),
                "severity": "warning",
                "confidence": 0.9,
                "relevant_character_ids": [character.id],
                "relevant_scene_ids": [scene.id],
                "evidence_refs": evidence,
            })

    by_position_and_character: dict[tuple[int, int], list[tuple[Any, Any, str]]] = defaultdict(list)
    confirmed_characters = [item for item in characters if item.confirmation_status == "writer_confirmed"]
    for scene in completed:
        if scene.timeline_context in _EXEMPT_CONTEXTS:
            continue
        cues = _character_cues(scene)
        location = _scene_location(scene, locations)
        if location is None or location.confirmation_status != "writer_confirmed":
            continue
        for character in confirmed_characters:
            aliases = {character.name.casefold(), *[alias.casefold() for alias in json.loads(character.aliases or "[]")]}
            cue = next((cues[name] for name in aliases if name in cues), None)
            if cue:
                by_position_and_character[(scene.timeline_position, character.id)].append((scene, location, cue))

    for (position, character_id), appearances in by_position_and_character.items():
        if len({location.id for _, location, _ in appearances}) < 2:
            continue
        character = next(item for item in confirmed_characters if item.id == character_id)
        scenes_at_position = sorted(appearances, key=lambda item: item[0].id)
        scene_a, location_a, cue_a = scenes_at_position[0]
        scene_b, location_b, cue_b = next(item for item in scenes_at_position[1:] if item[1].id != location_a.id)
        evidence = [
            {"kind": "scene_location", "id": scene_a.id, "label": scene_a.title, "text": cue_a,
             "location_id": location_a.id, "location": location_a.name, "timeline_position": position},
            {"kind": "scene_location", "id": scene_b.id, "label": scene_b.title, "text": cue_b,
             "location_id": location_b.id, "location": location_b.name, "timeline_position": position},
        ]
        candidates.append({
            "fingerprint": _fingerprint(project_id, "same_position_locations", evidence),
            "finding_type": "location_consistency",
            "description": (
                f"{character.name} has character cues in {location_a.name} and {location_b.name} "
                f"at the same explicitly assigned timeline position ({position}). Review whether the "
                "locations or timeline positions need clarification."
            ),
            "severity": "warning",
            "confidence": 0.85,
            "relevant_character_ids": [character_id],
            "relevant_scene_ids": [scene_a.id, scene_b.id],
            "evidence_refs": evidence,
        })

    event_by_id = {event.id: event for event in story_events}
    for dependent in story_events:
        if dependent.confirmation_status != "writer_confirmed" or dependent.timeline_position is None:
            continue
        for dependency_id in json.loads(dependent.dependency_event_ids or "[]"):
            prerequisite = event_by_id.get(dependency_id)
            if (
                prerequisite is None
                or prerequisite.project_id != project_id
                or prerequisite.confirmation_status != "writer_confirmed"
                or prerequisite.timeline_position is None
                or dependent.timeline_position > prerequisite.timeline_position
            ):
                continue
            evidence = [
                {"kind": "story_event", "id": prerequisite.id, "label": prerequisite.description,
                 "text": prerequisite.evidence or prerequisite.description, "timeline_position": prerequisite.timeline_position,
                 "role": "dependency"},
                {"kind": "story_event", "id": dependent.id, "label": dependent.description,
                 "text": dependent.evidence or dependent.description, "timeline_position": dependent.timeline_position,
                 "role": "dependent_event"},
            ]
            candidates.append({
                "fingerprint": _fingerprint(project_id, "event_dependency_order", evidence),
                "finding_type": "timeline_order",
                "description": (
                    f"The event '{dependent.description}' depends on '{prerequisite.description}', "
                    "but its explicitly assigned timeline position is not later. Review the ordering."
                ),
                "severity": "warning",
                "confidence": 1.0,
                "relevant_character_ids": sorted({character.id for character in dependent.characters}),
                "relevant_scene_ids": [],
                "evidence_refs": evidence,
            })
    return candidates
