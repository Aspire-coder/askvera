"""Deterministic, model-free resolution of unresolved back-references (A7).

"What about the other one?" after "...Kenya?" then "...Uganda?" must not
silently answer for whichever market was named most recently - that market is
the one reading "the other one" cannot mean. This module decides, from the
session's own USER turns and the current message alone, whether such a
reference:

- names its own market already, in which case nothing here applies (rule 1);
- is a closed-class CONTRASTIVE reference ("the other one" and its
  equivalents) with two or more distinct candidate markets already named in
  the user's own turns, which must produce a clarification naming the
  candidates rather than a guess (rule 2);
- is a closed-class ORDINAL reference ("the first one") that resolves
  deterministically to one candidate, by order of first mention (rule 3);
- has fewer than two candidate markets in play, or is written in a language
  this module does not recognize, in which case behaviour is unchanged
  (rules 4 and 5 - fail conservative).

No model call is made anywhere in this module. Candidate markets come from
the exact matchers app/orchestrator/chat_orchestrator.py already trusts for
this purpose (``find_market_mentions``, ``find_shared_office_record_countries``),
so a market this module did not itself invent a way to recognize is never
treated as a candidate. The closed-class word lists live in
config/reference_vocabulary.py, not here, and that module's docstring
explains why a closed grammatical class is safe to enumerate where an
open-ended phrase list would not be.

Deliberately duplicates chat_orchestrator._follow_up_tokens's tiny
normalization (NFKD-decompose, drop combining marks, casefold, split on word
characters) rather than importing it: chat_orchestrator calls into this
module, so importing the reverse direction would be a circular import for no
real benefit, since the function is a few lines of stdlib regex with no
state of its own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from services.market_config import find_market_mentions, find_shared_office_record_countries, market_display_name
from config.reference_vocabulary import LOCALIZED_CONTRASTIVE_TOKENS, LOCALIZED_ORDINAL_TOKENS


@dataclass(frozen=True)
class ReferenceResolution:
    """The outcome of checking one message for an unresolved back-reference."""

    # Two or more candidate market display names to ask the reader to choose
    # between (rule 2). Empty when no clarification is needed.
    clarification_candidates: tuple[str, ...] = field(default_factory=tuple)
    # The market an ordinal reference resolved to (rule 3), or None.
    resolved_market: str | None = None
    # ``message`` unchanged, or with the resolved market name appended so the
    # unmodified retrieval-query builder anchors it exactly as it would an
    # explicit market follow-up ("What about Kenya?"). Only differs from the
    # input message when resolved_market is set.
    rewritten_message: str = ""


def _tokens(text: str) -> tuple[str, ...]:
    decomposed = unicodedata.normalize("NFKD", text or "")
    unaccented = "".join(character for character in decomposed if not unicodedata.combining(character))
    return tuple(re.findall(r"[^\W_]+", unaccented.casefold(), flags=re.UNICODE))


def _language_code(language: str) -> str:
    return (language or "").split("-", 1)[0].split("_", 1)[0].strip().casefold()


def _user_turns(history: str) -> list[str]:
    """Extract prior USER turns only, matching chat_orchestrator's own parsing.

    Mirrors AIOrchestrator._user_messages_from_history: a "user:" line's
    content, in order. Assistant turns are never read - what Vera said is not
    a candidate market, only what the reader asked about is (A7 negative
    control: an assistant turn naming a market must not count).
    """
    turns: list[str] = []
    for line in (history or "").splitlines():
        role, separator, content = line.partition(":")
        if separator and role.strip().casefold() == "user":
            cleaned = content.strip()
            if cleaned:
                turns.append(cleaned)
    return turns


def _named_markets(message: str) -> list[str]:
    """Distinct market display names ``message`` itself names, in a stable order."""
    codes = find_market_mentions(message)
    names = {market_display_name(code) for code in codes} - {""}
    names |= find_shared_office_record_countries(message)
    return sorted(names)


def _candidate_markets(user_turns: list[str]) -> list[str]:
    """Distinct markets named across the session's user turns, oldest first."""
    ordered: list[str] = []
    for turn in user_turns:
        for name in _named_markets(turn):
            if name not in ordered:
                ordered.append(name)
    return ordered


def _resolve_ordinal(slot: str, candidates: list[str]) -> str | None:
    if slot == "first":
        return candidates[0]
    if slot == "last":
        return candidates[-1]
    if slot == "second" and len(candidates) >= 2:
        return candidates[1]
    if slot == "third" and len(candidates) >= 3:
        return candidates[2]
    if slot == "former" and len(candidates) == 2:
        return candidates[0]
    if slot == "latter" and len(candidates) == 2:
        return candidates[1]
    return None


def resolve_reference(message: str, history: str, language: str) -> ReferenceResolution:
    """Check ``message`` for an unresolved back-reference against ``history``.

    ``history`` is the session's rendered history text (the same string
    ``services.session.get_session_history`` returns); only its "user:"
    lines are read.
    """
    unresolved = ReferenceResolution(rewritten_message=message)
    language_code = _language_code(language)
    contrastive_tokens = LOCALIZED_CONTRASTIVE_TOKENS.get(language_code)
    ordinal_tokens = LOCALIZED_ORDINAL_TOKENS.get(language_code)
    if contrastive_tokens is None or ordinal_tokens is None:
        return unresolved  # rule 5: unknown language, unchanged behaviour

    if _named_markets(message):
        return unresolved  # rule 1: the message names its own market

    candidates = _candidate_markets(_user_turns(history))
    if len(candidates) < 2:
        return unresolved  # rule 4: nothing to disambiguate

    tokens = set(_tokens(message))
    if tokens & contrastive_tokens:
        # Rule 2 takes priority over rule 3 when a message happens to match
        # both: asking is always safe, guessing is not.
        return ReferenceResolution(clarification_candidates=tuple(candidates), rewritten_message=message)

    if "question" in tokens:
        # "my first question" / "the last question" already mean something
        # else entirely in this codebase - FOLLOW_UP_REFERENCE_MARKERS in
        # chat_orchestrator.py ("first question", "last question") reuses the
        # conversation's own opening question, not a candidate market. An
        # ordinal token next to "question" is that established meaning, not
        # this module's, so it is left alone rather than double-claimed.
        return unresolved
    matched_slot = next((slot for token, slot in ordinal_tokens.items() if token in tokens), None)
    if matched_slot is None:
        return unresolved  # no closed-class reference at all; leave untouched

    resolved = _resolve_ordinal(matched_slot, candidates)
    if resolved is None:
        return unresolved  # e.g. "latter" with 3+ candidates: genuinely ambiguous
    return ReferenceResolution(resolved_market=resolved, rewritten_message=f"{message} {resolved}".strip())
