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


def _query_is_safe_typo_rewrite(original: str, candidate: str) -> bool:
    original_tokens = _tokens(original)
    candidate_tokens = _tokens(candidate)
    if len(candidate_tokens) < 2 or candidate_tokens == original_tokens:
        return False

    original_numbers = [token for token in original_tokens if any(character.isdigit() for character in token)]
    candidate_numbers = [token for token in candidate_tokens if any(character.isdigit() for character in token)]
    if original_numbers != candidate_numbers:
        return False

    protected_acronyms = {
        token.casefold()
        for token in _raw_tokens(original)
        if 2 <= len(token) <= 5 and token.isupper() and token.isalpha()
    }
    if not protected_acronyms.issubset(set(candidate_tokens)):
        return False

    # Exact joined-word repairs are safe even when individual words cannot be
    # aligned to the original compact token.
    compact_candidate = "".join(candidate_tokens)
    if compact_candidate in original_tokens:
        return True

    repaired = False
    matched_original_indices: set[int] = set()
    for candidate_token in candidate_tokens:
        exact_index = next(
            (
                index
                for index, original_token in enumerate(original_tokens)
                if index not in matched_original_indices and candidate_token == original_token
            ),
            None,
        )
        if exact_index is not None:
            matched_original_indices.add(exact_index)
            continue
        repair_index = next(
            (
                index
                for index, original_token in enumerate(original_tokens)
                if index not in matched_original_indices
                and _token_is_repair(candidate_token, original_token)
            ),
            None,
        )
        if repair_index is None:
            return False
        matched_original_indices.add(repair_index)
        repaired = True
    return repaired


def safe_typo_ranking_queries(original: str, planned_queries: list[str], *, limit: int = 4) -> list[str]:
    """Return only planner queries proven to be bounded spelling repairs."""
    safe: list[str] = []
    for candidate in planned_queries:
        cleaned = " ".join((candidate or "").split()).strip()
        if cleaned and cleaned not in safe and _query_is_safe_typo_rewrite(original, cleaned):
            safe.append(cleaned)
        if len(safe) >= limit:
            break
    return safe
