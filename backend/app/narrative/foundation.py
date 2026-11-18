from ..schemas import FoundationElement, NarrativeElements, PremiseMention


def assess_foundation(
    elements: NarrativeElements,
    extractions: list[PremiseMention],
    story_facts: list[object] | None = None,
) -> list[FoundationElement]:
    """Summarize known foundations without scoring or treating missing details as errors."""
    by_category: dict[str, list[PremiseMention]] = {}
    for mention in extractions:
        by_category.setdefault(mention.category, []).append(mention)

    fact_aliases = {
        "protagonist": {"protagonist"},
        "character_goals": {"protagonist goal", "character goals", "goal"},
        "character_motivations": {"motivation", "character motivations"},
        "central_conflict": {"central conflict", "obstacles"},
        "stakes": {"stakes"},
        "antagonist": {"opposing force", "antagonistic force", "opposition"},
        "supporting_characters": {"supporting characters", "supporting character roles"},
        "important_relationships": {"important relationships", "relationships"},
        "setting": {"setting", "location", "time period", "world details"},
        "story_direction": {"story direction", "central dramatic question", "character journey", "ending"},
    }
    ordered_facts = sorted(story_facts or [], key=lambda fact: getattr(fact, "id", 0))
    facts_by_label = {
        getattr(fact, "label", "").casefold(): fact
        for fact in ordered_facts
    }
    definitions = [
        ("protagonist", "Protagonist", "protagonist", ("character_name", "character_role", "character"), "Who, if anyone, is the story centered on?"),
        ("character_goals", "Protagonist's goal", "character_goals", ("motivation_or_goal",), "What does the central character want to accomplish?"),
        ("character_motivations", "Motivation", "character_motivations", (), "What is known about why the character pursues this goal?"),
        ("central_conflict", "Central conflict", "central_conflict", (), "What opposition or difficulty complicates the goal?"),
        ("stakes", "Stakes", "stakes", (), "What might change or be at risk as the story develops?"),
        ("antagonist", "Opposing force", "antagonist", (), "Is there an opposing force, or is that not relevant to this story?"),
        ("supporting_characters", "Supporting characters", None, ("character_name", "character"), "Which other characters matter to the story?"),
        ("important_relationships", "Relationships", "important_relationships", ("relationship",), "Which relationships shape the story?"),
        ("setting", "Setting", "setting", ("location", "time_reference"), "Where and when does the story take place?"),
        ("story_direction", "Story direction", None, (), "What direction might the story take from here?"),
    ]
    assessed: list[FoundationElement] = []
    for key, label, field, hint_categories, prompt in definitions:
        element = getattr(elements, field) if field else None
        hints = [mention for category in hint_categories for mention in by_category.get(category, [])]
        matched_facts = [facts_by_label[name] for name in fact_aliases.get(key, set()) if name in facts_by_label]
        writer_fact = next(
            (fact for fact in reversed(matched_facts) if getattr(fact, "status", "") == "confirmed" and getattr(fact, "writer_confirmed", False)),
            None,
        )
        deferred_fact = next(
            (fact for fact in reversed(matched_facts) if getattr(fact, "intentionally_undecided", False)),
            None,
        )
        if writer_fact and getattr(writer_fact, "value", "").casefold() in {"not applicable", "none"}:
            status = "not_applicable"
            explanation = "The writer recorded that this element does not apply."
        elif deferred_fact:
            status = "intentionally_deferred"
            explanation = "The writer chose to leave this undecided for now."
        elif writer_fact:
            status = "established"
            explanation = "The writer recorded this in the Story Bible."
        elif element and element.status == "NOT_APPLICABLE":
            status = "not_applicable"
            explanation = element.explanation
        elif element and element.source == "writer" and element.intentionally_undecided:
            status = "intentionally_deferred"
            explanation = "The writer chose to leave this undecided for now."
        elif element and element.status == "EXPLICIT":
            status = "established"
            explanation = element.explanation
        elif element and element.status == "INFERRED":
            status = "partially_established"
            explanation = "There is an unconfirmed interpretation; the writer may review it."
        elif key == "supporting_characters" and (
            len({item.value for item in by_category.get("character_name", [])}) > 1
            or any(item.value.lower().startswith(("two ", "both ")) for item in by_category.get("character", []))
        ):
            status = "partially_established"
            explanation = "The premise names multiple characters, but does not identify supporting roles."
        elif key == "story_direction" and (
            elements.character_goals.status == "EXPLICIT" or elements.central_conflict.status == "EXPLICIT"
        ):
            status = "partially_established"
            explanation = "A stated goal or conflict gives the story some direction, while its broader course remains open."
        elif hints and key != "supporting_characters":
            status = "partially_established"
            explanation = "The premise contains related literal details, but does not establish this foundation fully."
        else:
            status = "undecided"
            explanation = "This is not established in the available story information."
        assessed.append(FoundationElement(
            key=key,
            label=label,
            status=status,
            explanation=explanation,
            next_consideration=prompt if status in {"partially_established", "undecided"} else None,
        ))
    return assessed
