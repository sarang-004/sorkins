from ..schemas import NarrativeElementKey, PremiseQuestionSuggestion


_OFFLINE_QUESTIONS: dict[NarrativeElementKey, str] = {
    "protagonist": "Who, if anyone, is the story centered on?",
    "central_conflict": "What central conflict, if any, complicates the story so far?",
    "character_goals": "What is the central character trying to accomplish?",
    "character_motivations": "What is known about why the character pursues this goal?",
    "stakes": "What could change or be at risk as the story develops?",
    "antagonist": "What opposing force, if any, affects the character's goal?",
    "external_conflict": "What external obstacle makes the character's goal difficult?",
    "internal_conflict": "What inner tension, if any, shapes the character's choices?",
    "important_relationships": "Which supporting characters or relationships shape the story, if any?",
    "setting": "Where and when does the story take place?",
    "central_dramatic_question": "What question would you like the audience to follow through the story?",
    "genre": "What genre, if any, are you exploring?",
    "theme": "What ideas, if any, are you interested in exploring?",
    "potential_structure": "What story shape, if any, feels useful to you?",
}


def offline_question(element_key: NarrativeElementKey) -> PremiseQuestionSuggestion:
    return PremiseQuestionSuggestion(
        element_key=element_key,
        question=_OFFLINE_QUESTIONS[element_key],
    )
