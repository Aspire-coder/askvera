"""Remove only verified inline citation syntax; structured citations remain."""
import re


def separate_verified_citations(answer: str, documents: list) -> str:
    values = []
    for document in documents:
        values.extend(str(value) for value in (
            document.id, document.title, document.page,
            document.metadata.get("section_id", ""),
        ) if value)
    lines = []
    for line in answer.splitlines():
        candidate = re.sub(r"\*", "", line).strip()
        if re.match(r"^(?:sources?\s*:|\[\d+\])", candidate, re.I):
            remainder = candidate
            matched = False
            for value in sorted(set(values), key=len, reverse=True):
                if value in remainder:
                    remainder = remainder.replace(value, " ")
                    matched = True
            remainder = re.sub(r"\[(\d+)\]", lambda m: " " if 1 <= int(m[1]) <= len(documents) else m[0], remainder)
            remainder = re.sub(r"\b(?:sources?|pages?|pp|section)\b", "", remainder, flags=re.I)
            if matched and not re.sub(r"[\s:.,;*\-]", "", remainder):
                continue
        lines.append(line)
    text = "\n".join(lines)
    # Full source IDs may contain section numbers. Remove only exact known
    # citation tokens before numeric validation; preserve surrounding whitespace.
    for identifier in {document.id for document in documents if document.id}:
        text = re.sub(r"\[" + re.escape(identifier) + r"\](?!\()", "", text)
    text = re.sub(
        r"\[(?:Source\s+)?(\d+)\]\(([^\s()]+)\)",
        lambda m: "" if (
            1 <= int(m[1]) <= len(documents)
            and m[2] == documents[int(m[1]) - 1].source
        ) else m[0],
        text, flags=re.I,
    )
    text = re.sub(r"\[(?:Source\s+)?(\d+)\](?!\()",
                  lambda m: "" if 1 <= int(m[1]) <= len(documents) else m[0], text, flags=re.I)
    # Parenthesized citation groups must not leave empty "()" or "(, )".
    text = re.sub(r"[ \t]*\([\s,;]*\)", "", text)
    # Empty citation headings/separators after verified citation removal.
    text = re.sub(r"(?:\n\s*(?:---|\*{0,2}Sources?\s*:\s*\*{0,2})\s*)+$", "", text, flags=re.I)
    return text.strip()
