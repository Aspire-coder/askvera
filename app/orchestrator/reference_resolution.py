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
  (rules 4 and 5 - fail conservative);
- names something OTHER than a market alongside the reference word ("the
  first ORDER", "the other FEE", "my first REQUIREMENT") - the message is
  then not a market reference at all, regardless of language or candidate
  count, and is left untouched (coordinator review, 2026-09-18; see
  ``_is_pure_reference`` and config/reference_vocabulary.py's
  LOCALIZED_NON_CONTENT_TOKENS / LOCALIZED_PROP_WORDS);
- puts a generic prop word ("one" and this module's other configured
  equivalents) BEFORE the ordinal word instead of after it (Fable review,
  2026-09-18, finding A1). "One second" is the common English interjection
  ("wait a moment"), not a reference to a second candidate market, whereas
  "the second one" is. Both phrases contain the exact same two tokens
  ("one", "second"); only their ORDER tells them apart, so
  ``_prop_word_precedes_ordinal`` additionally requires the ordinal word to
  precede the prop word before rule 3 may fire (see that function's
  docstring for why this is safe to apply to every configured language, not
  only English, even though only English exercises it today).

Fable also flagged that "Any other?" and "Is there another?" now trigger
rule 2's clarification. That is intentional, not a regression: both are
genuine contrastive references (English "other"/"another" plus only
closed-class opener words - "any", "is", "there" - all already listed in
LOCALIZED_NON_CONTENT_TOKENS), so under rule 2 asking which candidate is
meant is the correct, safe response - the same behaviour "What about the
other one?" gets. Two languages' worth of examples is not enough evidence to
special-case bare contrastive openers out of rule 2, and no general rule
suggested itself that would do so without also re-opening the false-positive
risk rule 2 exists to close; the coordinator's decision is to leave this
behaviour as designed.

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
from config.directory_field_vocabulary import normalize_language_code
from config.reference_vocabulary import (
    LOCALIZED_CONTRASTIVE_TOKENS,
    LOCALIZED_NON_CONTENT_TOKENS,
    LOCALIZED_ORDINAL_TOKENS,
    LOCALIZED_PROP_WORDS,
)


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
    """Fold a request-language tag the same way Lane B's directory-field
    vocabulary does (Fable review, 2026-09-18, finding A2), so a tag this
    module's own tables key by a different code - Norwegian's "nb"/"nb-NO"
    ("nb" folds to "no" here, matching every other localized vocabulary in
    this repository) or any bare "-region"/"_REGION" suffix ("fr-FR") -
    resolves instead of silently falling through rule 5 (unknown language)
    every time. ``config.directory_field_vocabulary`` has no dependency on
    this module or on ``app.orchestrator``, so importing its
    ``normalize_language_code`` here creates no import cycle.
    """
    return normalize_language_code(language)


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


def _is_pure_reference(tokens: set[str], matched: set[str], language_code: str) -> bool:
    """True when ``tokens``, once the closed-class opener/connector words and
    ``matched`` (the reference token(s) themselves) are removed, has nothing
    left but an allowed generic pronoun/place word (or nothing at all).

    This is the coordinator's fix (2026-09-18) for the false positives a bare
    token match produces: "the first ORDER", "the last DAY", "the other FEE"
    all match a closed-class word, but the word modifies real content, not a
    market. Only when the message is otherwise EMPTY of content does the
    reference word refer to a market candidate.
    """
    non_content = LOCALIZED_NON_CONTENT_TOKENS.get(language_code, frozenset())
    prop_words = LOCALIZED_PROP_WORDS.get(language_code, frozenset())
    leftover = tokens - non_content - matched
    return leftover <= prop_words


def _prop_word_precedes_ordinal(
    ordered_tokens: tuple[str, ...], ordinal_matched: set[str], prop_words: frozenset[str]
) -> bool:
    """True when a generic prop word ("one"/"ones" and this module's other
    configured equivalents) appears BEFORE the matched ordinal word in
    ``ordered_tokens`` - i.e. the message reads like "one second", the
    common English interjection, rather than "the second one" (Fable
    review, 2026-09-18, finding A1).

    Word order, not word choice, is what tells these two apart: "one" and
    "second" are present in both phrases. English's ordinal-noun-phrase
    order is fixed (an ordinal adjective always precedes the noun/pronoun
    it modifies - "the second one", never "one the second"), so requiring
    the ordinal to come first is a safe, general rule for English, applied
    here rather than special-cased to just the word "second".

    This check is written to run for every language this module configures,
    not only English, but today it can only ever change English's answer:
    LOCALIZED_PROP_WORDS's non-English entries (fr/de/nl/it/pt/es/fi/sv/no)
    are all COUNTRY/MARKET/PLACE nouns ("pays", "land", "maa", ...), never a
    generic "one"-type pronoun that also opens a fixed interjection the way
    English "one" does, so ``prop_words`` for those languages never appears
    in a message this function is asked to check, and the function returns
    False (order irrelevant) by simple absence. Documented here rather than
    skipped per-language so a future language whose LOCALIZED_PROP_WORDS
    table gains its own generic "one" word - and only if that language ALSO
    puts the ordinal after it in the same kind of interjection - inherits
    this protection automatically instead of needing its own carve-out; if
    such a language instead orders things the other way (prop-word-first is
    its NORMAL ordinal phrasing), this rule would wrongly reject its valid
    ordinal references and should be scoped out for that language's code
    specifically rather than applied blindly.
    """
    first_ordinal_index = next(
        (index for index, token in enumerate(ordered_tokens) if token in ordinal_matched), None
    )
    if first_ordinal_index is None:
        return False
    return any(token in prop_words for token in ordered_tokens[:first_ordinal_index])


def might_reference_market(message: str, language: str) -> bool:
    """Cheap, history-free pre-check: could ``message`` possibly need resolving?

    True does not guarantee ``resolve_reference`` will act - it still needs
    2+ candidate markets in the session's history, which this function never
    looks at. False *does* guarantee ``resolve_reference`` would return the
    message unchanged, so a caller that fetches history at real cost (a
    session-store read) can skip that read entirely for the common case of a
    message that names no bare, content-free reference at all - every other
    condition ``resolve_reference`` checks before it would ever read
    ``candidates`` (rules 1 and 5, plus the purity check above).
    """
    language_code = _language_code(language)
    contrastive_tokens = LOCALIZED_CONTRASTIVE_TOKENS.get(language_code)
    ordinal_tokens = LOCALIZED_ORDINAL_TOKENS.get(language_code)
    if contrastive_tokens is None or ordinal_tokens is None:
        return False  # rule 5: unknown language
    if _named_markets(message):
        return False  # rule 1: the message names its own market
    ordered_tokens = _tokens(message)
    tokens = set(ordered_tokens)
    contrastive_matched = tokens & contrastive_tokens
    if contrastive_matched and _is_pure_reference(tokens, contrastive_matched, language_code):
        return True
    ordinal_matched = {token for token in tokens if token in ordinal_tokens}
    if not ordinal_matched or not _is_pure_reference(tokens, ordinal_matched, language_code):
        return False
    prop_words = LOCALIZED_PROP_WORDS.get(language_code, frozenset())
    if _prop_word_precedes_ordinal(ordered_tokens, ordinal_matched, prop_words):
        return False  # A1: "one second", not "the second one"
    return True


def resolve_reference(message: str, history: str, language: str) -> ReferenceResolution:
    """Check ``message`` for an unresolved back-reference against ``history``.

    ``history`` is the session's rendered history text (the same string
    ``services.session.get_session_history`` returns); only its "user:"
    lines are read. Callers for whom fetching ``history`` has a real cost
    should call ``might_reference_market`` first and skip both the fetch and
    this call when it returns False.
    """
    unresolved = ReferenceResolution(rewritten_message=message)
    if not might_reference_market(message, language):
        return unresolved  # rules 1 and 5, and the purity check, need no history

    language_code = _language_code(language)
    contrastive_tokens = LOCALIZED_CONTRASTIVE_TOKENS[language_code]
    ordinal_tokens = LOCALIZED_ORDINAL_TOKENS[language_code]
    candidates = _candidate_markets(_user_turns(history))
    if len(candidates) < 2:
        return unresolved  # rule 4: nothing to disambiguate

    tokens = set(_tokens(message))
    if tokens & contrastive_tokens:
        # Rule 2 takes priority over rule 3 when a message happens to match
        # both: asking is always safe, guessing is not.
        return ReferenceResolution(clarification_candidates=tuple(candidates), rewritten_message=message)

    matched_slot = next((slot for token, slot in ordinal_tokens.items() if token in tokens), None)
    if matched_slot is None:
        return unresolved  # no closed-class reference at all; leave untouched

    resolved = _resolve_ordinal(matched_slot, candidates)
    if resolved is None:
        return unresolved  # e.g. "latter" with 3+ candidates: genuinely ambiguous
    return ReferenceResolution(resolved_market=resolved, rewritten_message=f"{message} {resolved}".strip())
