"""Conservative typo-rewrite validation for retrieval ranking.

Planner queries remain untrusted model output.  This module permits a planner
query to influence evidence ranking only when every material token can be
derived from the original question through a tightly bounded spelling repair.
It never changes the user message, locale filters, document scope, or evidence.
"""

from __future__ import annotations

import re
import unicodedata


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "").casefold()
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", _fold(value), flags=re.UNICODE)


def _raw_tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value or ""), flags=re.UNICODE)


def _damerau_levenshtein(left: str, right: str, max_distance: int) -> int:
    """Return a bounded optimal-string-alignment distance.

    The early length check keeps model-provided strings inexpensive to inspect.
    A value above ``max_distance`` is returned as ``max_distance + 1``.
    """
    if left == right:
        return 0
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous_previous: list[int] | None = None
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        row_minimum = left_index
        for right_index, right_character in enumerate(right, start=1):
            substitution = previous[right_index - 1] + int(left_character != right_character)
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            distance = min(substitution, insertion, deletion)
            if (
                previous_previous is not None
                and left_index > 1
                and right_index > 1
                and left_character == right[right_index - 2]
                and left[left_index - 2] == right_character
            ):
                distance = min(distance, previous_previous[right_index - 2] + 1)
            current.append(distance)
            row_minimum = min(row_minimum, distance)
        if row_minimum > max_distance:
            return max_distance + 1
        previous_previous, previous = previous, current
    return previous[-1]


def _token_is_repair(candidate: str, original: str) -> bool:
    if candidate == original:
        return False
    shorter, longer = sorted((candidate, original), key=len)
    if len(shorter) >= 5 and longer.startswith(shorter) and len(longer) - len(shorter) <= 4:
        return True
    max_distance = 1 if max(len(candidate), len(original)) < 10 else 2
    return _damerau_levenshtein(candidate, original, max_distance) <= max_distance


def _joined_parts(token: str, planned_token_groups: list[list[str]]) -> list[str]:
    for group in planned_token_groups:
        for start in range(len(group)):
            for size in (2, 3):
                parts = group[start : start + size]
                if len(parts) == size and "".join(parts) == token:
                    return parts
    return []


def _repair_token(token: str, planned_tokens: list[str]) -> str:
    candidates = {
        candidate
        for candidate in planned_tokens
        if candidate != token and _token_is_repair(candidate, token)
    }
    if not candidates:
        return token
    return min(
        candidates,
        key=lambda candidate: (
            _damerau_levenshtein(candidate, token, 2),
            abs(len(candidate) - len(token)),
            candidate,
        ),
    )


def safe_typo_ranking_queries(original: str, planned_queries: list[str], *, limit: int = 4) -> list[str]:
    """Rebuild the original query using only bounded token-level repairs.

    Extra words from planner output are never copied. Numbers and uppercase
    business acronyms are immutable. The return type remains a list for the
    scorer API, but at most one sanitized query is produced.
    """
    del limit
    original_tokens = _tokens(original)
    raw_tokens = _raw_tokens(original)
    if not original_tokens or len(raw_tokens) != len(original_tokens):
        return []
    planned_token_groups = [_tokens(query) for query in planned_queries if query]
    planned_tokens = [token for group in planned_token_groups for token in group]
    if not planned_tokens:
        return []

    repaired_tokens: list[str] = []
    repaired = False
    for index, token in enumerate(original_tokens):
        raw_token = raw_tokens[index]
        protected = any(character.isdigit() for character in token) or (
            2 <= len(raw_token) <= 5 and raw_token.isupper() and raw_token.isalpha()
        )
        if protected or token in planned_tokens:
            repaired_tokens.append(token)
            continue
        parts = _joined_parts(token, planned_token_groups)
        if parts:
            repaired_tokens.extend(parts)
            repaired = True
            continue
        repaired_token = _repair_token(token, planned_tokens)
        repaired_tokens.append(repaired_token)
        repaired = repaired or repaired_token != token

    return [" ".join(repaired_tokens)] if repaired else []
