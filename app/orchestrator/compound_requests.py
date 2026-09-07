"""Conservative syntax boundaries, not a safety or evidence classifier."""

import re


def separate_question_and_command(message: str) -> tuple[str, str] | None:
    """Keep both clauses verbatim; leave ambiguous requests on the normal path.

    ponytail: two explicit English clauses only. Expand through held-out language
    fixtures before accepting implicit, dependent or multilingual decomposition.
    """
    if any(char in message for char in ('"', '`', '{', '}', '“', '”')):
        return None
    parts = re.split(r"(?<=[?!.])\s+(?=(?:also\s+)?(?:what|how|which|when|where|does|do|is|are|"
                     r"write|create|draft|generate|make)\b)|;\s*", message.strip(), flags=re.I)
    if len(parts) != 2:
        return None
    questions = [part for part in parts if re.fullmatch(
        r"(?:what|how|which|when|where|does|do|is|are)\b[^?]+\?", part, re.I)]
    commands = [part for part in parts if re.match(r"(?:also\s+)?(?:write|create|draft|generate|make)\b", part, re.I)]
    if len(questions) != 1 or len(commands) != 1 or questions[0] == commands[0]:
        return None
    if re.search(r"\b(?:that|this|it|those|them|above|previous|following)\b", questions[0], re.I):
        return None
    return questions[0], commands[0]
