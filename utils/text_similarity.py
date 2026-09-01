"""Small, dependency-free string-similarity primitives shared across modules.

Kept separate from ``app.evidence`` and ``services.market_config`` (both of
which use ``edit_distance_at_most_one``) so neither has to import the other
just for this helper - ``app.evidence`` already imports from
``services.market_config``, so the reverse import would be circular.
"""

from __future__ import annotations


def edit_distance_at_most_one(left: str, right: str) -> bool:
    """Return true for one insertion, deletion, substitution, or transposition."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(differences) == 1:
            return True
        return (
            len(differences) == 2
            and differences[1] == differences[0] + 1
            and left[differences[0]] == right[differences[1]]
            and left[differences[1]] == right[differences[0]]
        )
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = 0
    long_index = 0
    skipped = False
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        if skipped:
            return False
        skipped = True
        long_index += 1
    return True
