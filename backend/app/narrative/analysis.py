import re

from ..schemas import (
    NarrativeElement,
    NarrativeElements,
    PremiseAnalysisResult,
    PremiseMention,
)


_ELEMENT_KEYS = (
    "protagonist", "antagonist", "central_conflict", "external_conflict",
    "internal_conflict", "character_motivations", "character_goals", "stakes",
    "genre", "setting", "theme", "central_dramatic_question",
    "important_relationships", "potential_structure",
)


def _undecided(key: str) -> NarrativeElement:
    return NarrativeElement(
        value=None,
        status="UNDECIDED",
        evidence=f"The premise does not explicitly establish {key.replace('_', ' ')}.",
        source="premise",
        confidence=0,
        explanation="No supported literal statement establishes this element.",
    )


def _explicit(value: str, evidence: str, explanation: str) -> NarrativeElement:
    return NarrativeElement(
        value=value,
        status="EXPLICIT",
        evidence=evidence,
        source="premise",
        confidence=1,
        explanation=explanation,
        writer_confirmed=False,
    )


def deterministic_analysis(
    premise: str,
    extractions: list[PremiseMention] | None = None,
) -> PremiseAnalysisResult:
    """Map only literal, evidence-backed extractions into narrative fields."""
    mentions = extractions or []
    elements = {key: _undecided(key) for key in _ELEMENT_KEYS}

    goals = [item for item in mentions if item.category == "motivation_or_goal"]
    if goals:
        goal = goals[0]
        elements["character_goals"] = _explicit(
            goal.value,
            goal.evidence,
            "This goal phrase is stated directly in the premise; it does not establish the character's motivation.",
        )

    locations = [item for item in mentions if item.category == "location"]
    if locations:
        location = locations[0]
        elements["setting"] = _explicit(
            location.value,
            location.evidence,
            "This location is named directly in the premise.",
        )

    relationships = [item for item in mentions if item.category == "relationship"]
    if relationships:
        relationship = relationships[0]
        elements["important_relationships"] = _explicit(
            relationship.value,
            relationship.evidence,
            "This relationship term appears directly in the premise; the system does not infer more detail.",
        )

    protagonist_marker = re.search(
        r"\b(?:protagonist|main character|central character|story follows|focuses on)\b"
        r"[^.!?;]*",
        premise,
        re.IGNORECASE,
    )
    if protagonist_marker:
        names = [item for item in mentions if item.category == "character_name"]
        evidence = protagonist_marker.group(0).strip()
        value = names[0].value if names and names[0].value in evidence else evidence
        elements["protagonist"] = _explicit(
            value,
            evidence,
            "The premise explicitly identifies this character or subject as the story's focus.",
        )

    conflict_marker = re.search(
        r"\b(?:conflict(?:s|ed|ing)?|struggles? against|must choose between|torn between)\b"
        r"[^.!?;]*",
        premise,
        re.IGNORECASE,
    )
    if conflict_marker:
        evidence = conflict_marker.group(0).strip()
        elements["central_conflict"] = _explicit(
            evidence,
            evidence,
            "The premise explicitly describes a conflict or incompatible choices.",
        )

    external_marker = re.search(
        r"\b(?:struggles? against|fights? against|is pursued by|must evade|"
        r"opposed by|at odds with|under attack from)\b[^.!?;]*",
        premise,
        re.IGNORECASE,
    )
    if external_marker:
        evidence = external_marker.group(0).strip()
        elements["external_conflict"] = _explicit(
            evidence,
            evidence,
            "The premise directly names an external obstacle or opposing force.",
        )

    internal_marker = re.search(
        r"\b(?:torn between|struggles with (?:their|his|her) own|inner conflict|"
        r"conflicted about|cannot decide whether)\b[^.!?;]*",
        premise,
        re.IGNORECASE,
    )
    if internal_marker:
        evidence = internal_marker.group(0).strip()
        elements["internal_conflict"] = _explicit(
            evidence,
            evidence,
            "The premise directly describes an internal conflict.",
        )

    stakes_marker = re.search(
        r"\b(?:risks? losing|at stake is|could lose|must save|before .{1,80} is too late)\b"
        r"[^.!?;]*",
        premise,
        re.IGNORECASE,
    )
    if stakes_marker:
        evidence = stakes_marker.group(0).strip()
        elements["stakes"] = _explicit(evidence, evidence, "The consequence or stake is stated directly in the premise.")

    antagonist_marker = re.search(r"\b(?:no|without) (?:conventional )?(?:antagonist|villain)\b", premise, re.I)
    if antagonist_marker:
        evidence = antagonist_marker.group(0)
        elements["antagonist"] = NarrativeElement(
            value=None,
            status="NOT_APPLICABLE",
            evidence=evidence,
            source="premise",
            confidence=1,
            explanation="The premise explicitly says there is no conventional antagonist.",
        )
        antagonist_classification = "no_conventional_antagonist"
    else:
        antagonist_classification = "undecided"

    return PremiseAnalysisResult(
        premise=premise,
        narrative_elements=NarrativeElements(**elements),
        antagonist_classification=antagonist_classification,
    )
