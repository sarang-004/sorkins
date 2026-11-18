import re

from ..schemas import PremiseMention


_CHARACTER_PATTERN = re.compile(
    r"\b(?:a|an|the|two|both|one of the)\s+"
    r"(?:(?:retired|successful|estranged|young|old|middle-aged|middle aged|elderly|"
    r"teenage|adult|mysterious|unidentified|former|wealthy|poor)\s+)*"
    r"(?:serial killer|detective|doctor|teacher|nurse|lawyer|journalist|politician|businessman|businesswoman|woman|man|"
    r"brothers?|sisters?|father|mother|child|children|girl|boy|stranger|individual|person|family)\b",
    re.IGNORECASE,
)
_TIME_PATTERN = re.compile(
    r"\b(?:\d{4}|\d+\s+(?:years?|months?|weeks?|days?)\s+ago|"
    r"(?:last|next)\s+(?:year|month|week|day)|"
    r"(?:yesterday|today|tomorrow|recently|formerly|meanwhile|years? later|"
    r"flashbacks?|flash forwards?|(?:final|first|second|third)\s+act))\b",
    re.IGNORECASE,
)
_OBJECT_PATTERN = re.compile(
    r"\b(?:letters?|package|photographs?|documents?|keys?|weapon|"
    r"(?:family\s+)?house)\b",
    re.I,
)
_ROLE_PATTERN = re.compile(
    r"\b(?:a|an|the)\s+(?:(?:retired|successful|estranged|young|old|middle-aged|middle aged|"
    r"elderly|teenage|adult|mysterious|former|wealthy|poor)\s+)*"
    r"(?P<role>doctor|physician|surgeon|detective|teacher|nurse|lawyer|journalist|"
    r"police officer|soldier|pilot|artist|writer|politician|scientist|student)\b",
    re.IGNORECASE,
)
_NAMED_CHARACTER_PATTERN = re.compile(
    r"\b(?:named|called|story follows|focuses on)\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
)
_LOCATION_PATTERN = re.compile(
    r"\b(?:(?:small|coastal|rural|remote|nearby|local)\s+){0,2}"
    r"(?:hometown|doorstep|home|village|city|town)\b",
    re.I,
)
_ORGANIZATION_PATTERN = re.compile(
    r"\b(?:police department|city council|company|corporation|university|hospital|"
    r"government|agency|organization|organisation|firm|FBI|CIA|NASA|Interpol|United Nations)\b",
    re.IGNORECASE,
)
_RELATIONSHIP_PATTERN = re.compile(
    r"\b(?:estranged brothers?|brothers?|sisters?|father|mother|family|"
    r"(?:her|his|their|our)\s+(?:father|mother|brother|sister|husband|wife|child|parent)|"
    r"(?:separated?|separating)\s+from\s+(?:(?:her|his|their)\s+)?(?:husband|wife|partner)|"
    r"his wife|her husband|their child|father's death|mother's death)\b",
    re.IGNORECASE,
)
_MOTIVATION_PATTERN = re.compile(
    r"\b(?:wants? to|hopes? to|intends? to|plans? to|aims? to|"
    r"seeks? to|decides? to|goal is to|dreams? of|"
    r"to\s+(?:start|begin|rebuild|try|investigate|find|save|protect|stop|expose|"
    r"discover|rescue|return|escape|prevent|restore|change|prove|uncover))\b",
    re.IGNORECASE,
)
_GOAL_PHRASE_PATTERN = re.compile(
    r"\b(?:(?:wants? to|hopes? to|intends? to|plans? to|aims? to|seeks? to|"
    r"decides? to|goal is to|dreams? of|in order to)\s+|"
    r"to\s+(?=(?:start|begin|rebuild|try|investigate|find|save|protect|stop|expose|"
    r"discover|rescue|return|escape|prevent|restore|change|prove|uncover)\b))"
    r"(?P<goal>[^,;.!?]+)",
    re.IGNORECASE,
)
_ACTION_PATTERN = re.compile(
    r"\b(?:receiv(?:e|es|ed|ing)|arrest(?:s|ed|ing)?|investigat(?:e|es|ed|ing)|"
    r"commit(?:s|ted|ting)?|struggl(?:e|es|ed|ing)|return(?:s|ed|ing)?|"
    r"disappear(?:s|ed|ing)?|search(?:es|ed|ing)?|pursu(?:e|es|ed|ing)|"
    r"fight(?:s|ing)?|hid(?:e|es|ing)?|prevent(?:s|ed|ing)?|"
    r"arriv(?:e|es|ed|ing)|abandon(?:s|ed|ing)?|discover(?:s|ed|ing)?|"
    r"die(?:s|d|ing)?|send(?:s|ing)?|los(?:e|es|t|ing)|separat(?:e|es|ed|ing)|"
    r"mov(?:e|es|ed|ing)|sell|sells|sold|preserv(?:e|es|ed|ing)|"
    r"insist(?:s|ed|ing)?|rebuild(?:s|ing)?|reveal(?:s|ed|ing)?|"
    r"decid(?:e|es|ed|ing)|start(?:s|ed|ing)?|work(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_CLAUSE_SEPARATOR = re.compile(
    r"(?<=[.!?;])\s+|\s+\b(?:and|but)\b\s+",
    re.IGNORECASE,
)


def _mention(category: str, premise: str, start: int, end: int) -> PremiseMention:
    excerpt = premise[start:end]
    return PremiseMention(
        category=category,
        value=excerpt,
        evidence=excerpt,
        source="premise",
        source_start=start,
        source_end=end,
        extraction_method="regex",
        confirmation_status="unconfirmed",
    )


def parse_premise(premise: str) -> list[PremiseMention]:
    """Extract only literal mentions using conservative patterns; never infer story roles."""
    matches: list[tuple[int, int, PremiseMention]] = []
    patterns = (
        ("character", _CHARACTER_PATTERN),
        ("character_role", _ROLE_PATTERN),
        ("character_name", _NAMED_CHARACTER_PATTERN),
        ("character_description", re.compile(
            r"\b(?:a|an|the|two|both|one of the)\s+"
            r"(?:(?:retired|successful|estranged|young|old|middle-aged|middle aged|elderly|"
            r"teenage|adult|mysterious|unidentified|former|wealthy|poor)\s+)+"
            r"(?:serial killer|detective|politician|businessman|businesswoman|woman|man|"
            r"brothers?|sisters?|father|mother|child|children|girl|boy|stranger|individual|person|family)\b",
            re.IGNORECASE,
        )),
        ("organization", _ORGANIZATION_PATTERN),
        ("time_reference", _TIME_PATTERN),
        ("object", _OBJECT_PATTERN),
        ("location", _LOCATION_PATTERN),
        ("relationship", _RELATIONSHIP_PATTERN),
    )
    for category, pattern in patterns:
        for match in pattern.finditer(premise):
            span = (
                match.span("name") if category == "character_name"
                else match.span("role") if category == "character_role"
                else match.span()
            )
            matches.append((span[0], span[1], _mention(category, premise, *span)))

    clause_start = 0
    separators = list(_CLAUSE_SEPARATOR.finditer(premise))
    for separator in [*separators, None]:
        clause_end = separator.start() if separator else len(premise)
        raw_clause = premise[clause_start:clause_end]
        leading_space = len(raw_clause) - len(raw_clause.lstrip())
        clause = raw_clause.strip()
        clause_start += leading_space
        if not clause:
            clause_start = separator.end() if separator else clause_end
            continue
        clause_length = len(clause)
        for action in _ACTION_PATTERN.finditer(clause):
            action_start = clause_start + action.start()
            action_end = clause_start + action.end()
            matches.append((
                action_start,
                action_end,
                _mention("action", premise, action_start, action_end),
            ))
        if _ACTION_PATTERN.search(clause):
            matches.append((
                clause_start,
                clause_start + clause_length,
                _mention("event", premise, clause_start, clause_start + clause_length),
            ))
        if _MOTIVATION_PATTERN.search(clause):
            goal = _GOAL_PHRASE_PATTERN.search(clause)
            if goal:
                goal_start = clause_start + goal.start("goal")
                goal_end = clause_start + goal.end("goal")
            else:
                goal_start, goal_end = clause_start, clause_start + clause_length
            matches.append((goal_start, goal_end, _mention("motivation_or_goal", premise, goal_start, goal_end)))
        clause_start = separator.end() if separator else clause_end

    unique: dict[tuple[str, str], PremiseMention] = {}
    for _, _, item in sorted(matches, key=lambda match: (match[0], match[1], match[2].category)):
        unique.setdefault((item.category, item.value), item)
    return list(unique.values())
