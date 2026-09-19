"""Shared whole-segment matching for directory ``record_country`` values.

One implementation used by both ``app/orchestrator/chat_orchestrator.py``
(support-contact and directory-field targeting) and
``app/response/outcome.py`` (international-directory classification), so the
two can never drift apart.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_SEGMENT_SPLIT_RE = re.compile(r"[/\s]+")


def record_segments(value: str) -> list[str]:
    """Split a directory ``record_country`` (or a market name) into lower-cased
    word segments on both "/" and whitespace - "Kenya/East Africa" ->
    ["kenya", "east", "africa"]."""
    return [part.casefold() for part in _SEGMENT_SPLIT_RE.split(value.strip()) if part]


def record_matches_any_target(record_country: str, target_names: Sequence[str]) -> bool:
    """True only for a whole-segment/word match - never a region word (``East
    Africa``, ``Benelux``) or a country named only inside a record's body."""
    tokens = record_segments(record_country)
    for name in target_names:
        name_words = record_segments(name)
        width = len(name_words)
        if not width or width > len(tokens):
            continue
        if any(tokens[start:start + width] == name_words for start in range(len(tokens) - width + 1)):
            return True
    return False
