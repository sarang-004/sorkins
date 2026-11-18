from ..schemas import NarrativeElementKey, NarrativeElements


GAP_PRIORITY: tuple[NarrativeElementKey, ...] = (
    "protagonist",
    "character_goals",
    "central_conflict",
    "stakes",
    "external_conflict",
    "character_motivations",
    "internal_conflict",
    "antagonist",
    "important_relationships",
    "setting",
    "central_dramatic_question",
)

GAP_IMPORTANCE: dict[NarrativeElementKey, str] = {
    "protagonist": "CRITICAL",
    "central_conflict": "CRITICAL",
    "character_goals": "CRITICAL",
    "character_motivations": "IMPORTANT",
    "stakes": "IMPORTANT",
    "antagonist": "OPTIONAL",
    "external_conflict": "OPTIONAL",
    "internal_conflict": "OPTIONAL",
    "important_relationships": "OPTIONAL",
    "setting": "OPTIONAL",
    "central_dramatic_question": "OPTIONAL",
}


def unresolved_gaps(elements: NarrativeElements) -> list[NarrativeElementKey]:
    return [
        key for key in GAP_PRIORITY
        if getattr(elements, key).status in {"INFERRED", "UNDECIDED"}
        and not (
            getattr(elements, key).source == "writer"
            and getattr(elements, key).status == "UNDECIDED"
        )
    ]


def gap_records(elements: NarrativeElements) -> list[dict[str, str]]:
    return [
        {"element_key": key, "importance": GAP_IMPORTANCE[key]}
        for key in unresolved_gaps(elements)
    ]


def next_gap(
    elements: NarrativeElements,
    previously_asked: set[NarrativeElementKey],
) -> NarrativeElementKey | None:
    return next(
        (
            key
            for key in unresolved_gaps(elements)
            if key not in previously_asked
        ),
        None,
    )
