"""Conservative typo-rewrite validation for retrieval ranking.

Planner queries remain untrusted model output.  This module permits a planner
query to influence evidence ranking only when every material token can be
derived from the original question through a tightly bounded spelling repair.
It never changes the user message, locale filters, document scope, or evidence.
"""

from __future__ import annotations

import re
import unicodedata


_SPLIT_REPAIR_PROTECTED_PARTS = frozenset(
    {
        "a", "an", "and", "are", "at", "be", "but", "by", "can", "do", "for",
        "from", "have", "i", "in", "is", "it", "me", "my", "no", "not", "of",
        "on", "or", "the", "to", "was", "we", "what", "with", "you",
    }
)
_SEMANTIC_COLLISION_PAIRS = frozenset({frozenset({"shipping", "shopping"})})

# Physical QWERTY key neighbours (same-row neighbours plus the keys touching a
# key diagonally on the row above/below), used only to decide whether a
# single-character *substitution* looks like a plausible fat-finger slip.
# This assumes a QWERTY-like physical layout. To support another layout
# (AZERTY, Dvorak, a non-Latin keyboard, ...), build an equivalent adjacency
# map for that layout's physical key positions and pass/select it instead of
# hard-coding this table.
_QWERTY_ADJACENCY: dict[str, frozenset[str]] = {
    "q": frozenset("wa"),
    "w": frozenset("qeas"),
    "e": frozenset("wrsd"),
    "r": frozenset("etdf"),
    "t": frozenset("ryfg"),
    "y": frozenset("tugh"),
    "u": frozenset("yihj"),
    "i": frozenset("uojk"),
    "o": frozenset("ipkl"),
    "p": frozenset("ol"),
    "a": frozenset("qwsz"),
    "s": frozenset("awedzx"),
    "d": frozenset("serfxc"),
    "f": frozenset("drtgcv"),
    "g": frozenset("ftyhvb"),
    "h": frozenset("gyujbn"),
    "j": frozenset("huiknm"),
    "k": frozenset("jiolm"),
    "l": frozenset("kop"),
    "z": frozenset("asx"),
    "x": frozenset("zsdc"),
    "c": frozenset("xdfv"),
    "v": frozenset("cfgb"),
    "b": frozenset("vghn"),
    "n": frozenset("bhjm"),
    "m": frozenset("njk"),
}

# A single-character substitution or an adjacent-character transposition is
# just as easy to produce between two *different, independently valid*
# English words (quite/quiet, form/from, trial/trail) as it is to produce as
# an actual typo. Below this length the space of short real words is dense
# enough that those "symmetric" edit shapes are not, by themselves, good
# evidence of a misspelling; only a deletion/insertion that removes or adds
# one occurrence of an already-repeated letter (see
# ``_repeated_letter_edit``) is trusted at any length, because that shape is
# directional and rare between two unrelated real words.
_MIN_LENGTH_FOR_SYMMETRIC_REPAIR = 6


def _keyboard_adjacent(left: str, right: str) -> bool:
    return right in _QWERTY_ADJACENCY.get(left, frozenset())


def _repeated_letter_edit(shorter: str, longer: str) -> bool:
    """True if ``longer`` becomes ``shorter`` by dropping one occurrence of a
    letter that still appears elsewhere in ``longer`` (not necessarily
    adjacent to the dropped occurrence).

    Typing a letter that already recurs in the word (recognized, order,
    sponsoring, requirements, international, conditions) is where people
    reliably drop or double a keystroke; that repetition is what makes the
    edit look like a genuine slip rather than a coincidental near-miss with
    an unrelated real word.
    """
    for index, letter in enumerate(longer):
        if longer[:index] + longer[index + 1 :] == shorter and longer.count(letter) >= 2:
            return True
    return False


def _looks_like_typo_shape(candidate: str, original: str) -> bool:
    """Require the single edit between ``candidate`` and ``original`` to look
    like a plausible typing slip, not merely a nearby word.
    """
    if len(candidate) == len(original):
        diff_positions = [index for index in range(len(candidate)) if candidate[index] != original[index]]
        if len(diff_positions) == 1:
            if min(len(candidate), len(original)) < _MIN_LENGTH_FOR_SYMMETRIC_REPAIR:
                return False
            index = diff_positions[0]
            return _keyboard_adjacent(candidate[index], original[index])
        if len(diff_positions) == 2 and diff_positions[1] == diff_positions[0] + 1:
            if min(len(candidate), len(original)) < _MIN_LENGTH_FOR_SYMMETRIC_REPAIR:
                return False
            first, second = diff_positions
            return candidate[first] == original[second] and candidate[second] == original[first]
        return False
    shorter, longer = (candidate, original) if len(candidate) < len(original) else (original, candidate)
    if len(longer) - len(shorter) != 1:
        return False
    return _repeated_letter_edit(shorter, longer)


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
    max_distance = 1 if max(len(candidate), len(original)) < 10 else 2
    return _damerau_levenshtein(candidate, original, max_distance) <= max_distance


def _is_semantic_collision(candidate: str, original: str) -> bool:
    return frozenset({candidate, original}) in _SEMANTIC_COLLISION_PAIRS


def _joined_parts(token: str, planned_token_groups: list[list[str]]) -> list[str]:
    for group in planned_token_groups:
        for start in range(len(group)):
            for size in (2, 3):
                parts = group[start : start + size]
                if len(parts) == size and "".join(parts) == token:
                    return parts
    return []


def _split_repair(
    tokens: list[str], raw_tokens: list[str], index: int, planned_tokens: list[str]
) -> tuple[str, int] | None:
    """Collapse two or three accidentally split fragments into one planned word."""
    for size in (3, 2):
        if index + size > len(tokens):
            continue
        joined = "".join(tokens[index : index + size])
        if (
            len(joined) < 5
            or any(len(part) < 2 for part in tokens[index : index + size])
            or any(part in _SPLIT_REPAIR_PROTECTED_PARTS for part in tokens[index : index + size])
            or any(any(character.isdigit() for character in part) for part in tokens[index : index + size])
            or any(
                2 <= len(raw_part) <= 5 and raw_part.isupper() and raw_part.isalpha()
                for raw_part in raw_tokens[index : index + size]
            )
        ):
            continue
        for candidate in planned_tokens:
            if any(character.isdigit() for character in candidate):
                continue
            if not _is_semantic_collision(candidate, joined) and (
                candidate == joined
                or (_token_is_repair(candidate, joined) and _looks_like_typo_shape(candidate, joined))
            ):
                return candidate, size
    return None


def _repair_token(token: str, planned_tokens: list[str]) -> str:
    if len(token) < 4:
        return token
    candidates = {
        candidate
        for candidate in planned_tokens
        if candidate != token
        and _token_is_repair(candidate, token)
        and not _is_semantic_collision(candidate, token)
        and (len(token) >= 5 or abs(len(candidate) - len(token)) == 1)
        and _looks_like_typo_shape(candidate, token)
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
    index = 0
    while index < len(original_tokens):
        token = original_tokens[index]
        raw_token = raw_tokens[index]
        protected = any(character.isdigit() for character in token) or (
            2 <= len(raw_token) <= 5 and raw_token.isupper() and raw_token.isalpha()
        )
        if protected or token in planned_tokens:
            repaired_tokens.append(token)
            index += 1
            continue
        split_repair = _split_repair(original_tokens, raw_tokens, index, planned_tokens)
        if split_repair:
            repaired_token, consumed = split_repair
            repaired_tokens.append(repaired_token)
            repaired = True
            index += consumed
            continue
        parts = _joined_parts(token, planned_token_groups)
        if parts:
            repaired_tokens.extend(parts)
            repaired = True
            index += 1
            continue
        repaired_token = _repair_token(token, planned_tokens)
        repaired_tokens.append(repaired_token)
        repaired = repaired or repaired_token != token
        index += 1

    return [" ".join(repaired_tokens)] if repaired else []
