import re

from ..schemas import PremiseAnalysisResult


_NON_SUBSTANTIVE_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "as", "at", "by",
    "for", "from", "in", "into", "of", "on", "to", "with", "and", "or", "but", "that", "this",
    "their", "his", "her", "its", "they", "them", "he", "she", "it", "who", "which", "may",
    "might", "could", "possibly", "potentially", "likely", "perhaps", "possible", "probably",
    "unconfirmed", "interpretation", "interpreted", "inferred", "protagonist", "antagonist",
    "force", "conflict", "goal", "goals", "motivation", "motivations", "stakes", "theme",
    "setting", "genre", "relationship", "relationships", "structure", "question", "central",
}

_ELEMENT_KEYS = (
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
)
_PROTAGONIST_MARKER = re.compile(
    r"\b(?:protagonist|main character|central character|story follows|focuses on)\b",
    re.IGNORECASE,
)
_MOTIVATION_OR_GOAL_MARKER = re.compile(
    r"\b(?:wants? to|hopes? to|intends? to|plans? to|aims? to|seeks? to|"
    r"decides? to|goal is to|motivated by|dreams? of|"
    r"to\s+(?:start|begin|rebuild|try))\b",
    re.IGNORECASE,
)


def _substantive_words(text: str) -> set[str]:
    return {
        word.lower()
        for word in re.findall(r"[A-Za-z0-9']+", text)
        if word.lower() not in _NON_SUBSTANTIVE_WORDS
    }


def validate_analysis(analysis: PremiseAnalysisResult) -> PremiseAnalysisResult:
    for key in _ELEMENT_KEYS:
        element = getattr(analysis.narrative_elements, key)
        element.writer_confirmed = False
        element.intentionally_undecided = False
        if element.status == "EXPLICIT" and (
            element.value not in analysis.premise
            or element.evidence not in analysis.premise
            or element.value not in element.evidence
        ):
            element.status = "UNDECIDED"
            element.value = None
            element.evidence = "No exact premise excerpt establishes this element."
            element.source = "premise"
            element.confidence = 0
            element.explanation = "No literal premise excerpt supports the proposed value."
        elif (
            key == "protagonist"
            and element.status == "EXPLICIT"
            and not _PROTAGONIST_MARKER.search(element.evidence)
        ):
            excerpt = element.evidence
            element.status = "INFERRED"
            element.evidence = (
                f'Interpretation only; premise excerpt: "{excerpt}"; '
                "this does not explicitly establish the protagonist role."
            )
            element.source = "ai_inference"
            element.confidence = min(element.confidence or 0.5, 0.6)
            element.explanation = (
                "The character is named in the premise, but their protagonist role is an interpretation."
            )
        elif (
            key in {"character_motivations", "character_goals"}
            and element.status in {"EXPLICIT", "INFERRED"}
            and not _MOTIVATION_OR_GOAL_MARKER.search(element.evidence)
        ):
            element.status = "UNDECIDED"
            element.value = None
            element.evidence = (
                "The premise does not directly state a character motivation or goal."
            )
            element.source = "premise"
            element.confidence = 0
            element.explanation = "No direct motivation or goal statement appears in the cited premise text."
        elif element.status == "INFERRED":
            excerpt = re.search(r'premise excerpt:\s*"([^"]+)"', element.evidence, re.IGNORECASE)
            if (
                "interpretation only" not in element.evidence.lower()
                or excerpt is None
                or excerpt.group(1) not in analysis.premise
                or not _substantive_words(element.value or "").issubset(
                    _substantive_words(excerpt.group(1))
                )
            ):
                element.status = "UNDECIDED"
                element.value = None
                element.evidence = (
                    "The premise does not provide a clearly cited basis for this interpretation."
                )
                element.source = "premise"
                element.confidence = 0
                element.explanation = "The cited excerpt does not support this interpretation."
            else:
                element.source = "ai_inference"
        elif element.status == "NOT_APPLICABLE" and element.evidence not in analysis.premise:
            element.status = "UNDECIDED"
            element.value = None
            element.evidence = (
                "The premise does not establish that this element is not applicable."
            )
            element.source = "premise"
            element.confidence = 0
            element.explanation = "The premise does not establish that this element is irrelevant."
        elif element.status in {"EXPLICIT", "UNDECIDED", "NOT_APPLICABLE"}:
            element.source = "premise"
        element.writer_confirmed = (
            element.source == "premise"
            and element.status in {"EXPLICIT", "NOT_APPLICABLE"}
        )
        element.intentionally_undecided = False

    antagonist = analysis.narrative_elements.antagonist
    classification = analysis.antagonist_classification
    premise_lower = analysis.premise.lower()
    explicit_role_is_named = bool(
        re.search(r"\b(antagonist|villain|enemy|adversary|opponent)\b", premise_lower)
    )
    explicitly_no_antagonist = bool(
        re.search(
            r"\b(no|without)\s+(?:conventional\s+)?(?:antagonist|villain)\b",
            premise_lower,
        )
    )
    classification_matches = {
        "explicit_antagonist": antagonist.status == "EXPLICIT" and explicit_role_is_named,
        "potential_antagonist": antagonist.status == "INFERRED",
        "antagonistic_force": antagonist.status in {"EXPLICIT", "INFERRED"},
        "no_conventional_antagonist": (
            antagonist.status in {"EXPLICIT", "INFERRED", "NOT_APPLICABLE"}
            and explicitly_no_antagonist
        ),
        "undecided": antagonist.status == "UNDECIDED",
    }
    if not classification_matches[classification]:
        antagonist.status = "UNDECIDED"
        antagonist.value = None
        antagonist.evidence = (
            "The premise does not establish whether an antagonist exists or what form any "
            "antagonistic force takes."
        )
        antagonist.source = "premise"
        antagonist.confidence = 0
        antagonist.explanation = "The premise does not establish an antagonist or antagonistic force."
        analysis.antagonist_classification = "undecided"
    return analysis
