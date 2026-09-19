"""Lane 5 (CX phase 3): safe typo clarification and conversation repair.

Two independent, pure, deterministic capabilities, both model-free:

1. ``typo_clarification`` - when a question contains a typo-shaped near-miss
   of the one semantic-collision pair ``app/retrieval/typo_safety.py``
   (Codex-owned) already defines - English "shipping"/"shopping", one
   QWERTY-adjacent letter apart - and the sentence gives no other clue which
   one was meant, return a single ``clarify_field`` question naming both
   readable options instead of silently guessing (or silently repairing,
   which is what ``typo_safety`` already does for every *unambiguous* typo -
   this module only ever adds a question for the ambiguous residue).
2. ``detect_repair`` - recognise the user correcting their OWN previous turn
   ("no, I meant Ghana", "not Kenya, Uganda", "sorry, I meant the delivery
   cost") in any of the 12 route languages, and produce the rewritten,
   standalone form of the previous question with the corrected span swapped
   in - so retrieval can be re-run against it exactly as if the reader had
   asked the corrected question directly.
3. ``one_question`` - the shared, cross-lane precedence rule: never ask the
   reader two things in the same turn.

Every user-visible sentence is a message key
(``docs/conversation-quality/phase3/CX_LANES.md``'s table: ``clarify_field``,
``clarify_country``, ``clarify_role``, ``repair_ack``), never inlined English
copy - this module returns the key name and the placeholder values only.
Lane 4's renderer (``app/response/cx_render.py``) turns a key + placeholders
into localized text; nothing here imports it, so this module stays usable
before Lane 4 exists and keeps its own tests free of any dependency on
copy content.

Nothing here changes retrieval, ranking, evidence approval or country
authorization. A ``market`` :class:`Repair` is a DIRECTORY/target change only
(which market's directory record - phone, address, delivery cost - the
follow-up should be read against); it must never be read as changing which
country's POLICY governs the answer. The session's own ``country`` field
keeps doing that, exactly as before this module existed; nothing in this
module's return types (:class:`Repair`, :class:`Clarification`) carries a
policy-country field at all, so there is nothing here a caller could
mistakenly wire into policy authorization even by accident.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.retrieval.typo_safety import (
    _damerau_levenshtein as _typo_distance,
    _looks_like_typo_shape as _typo_shape_matches,
)
from config.directory_field_vocabulary import normalize_language_code
from config.repair_vocabulary import (
    CONTEXT_DISAMBIGUATION_WORDS,
    MEANT_CUE_PHRASES,
    NOT_CUE_WORDS,
    SHIPPING_BARE_WORD,
    SHIPPING_OPTION_LABEL,
    SHOPPING_BARE_WORD,
    SHOPPING_OPTION_LABEL,
    TOPIC_REPLACEMENT_WORDS,
)
from services.market_config import find_market_mentions, market_display_name

# Precedence for `one_question`: reference ambiguity outranks a directory
# country choice, which outranks a role choice, which outranks a bare field
# choice - each earlier kind is a broader fork in the conversation than the
# next (which market, then which record within that market, then which
# field within that record). Reference ambiguity itself is resolved by
# app.orchestrator.reference_resolution, upstream of this module; its
# "reference" clarification is included here only so a caller that also has
# a reference-resolution result can hand it to the same `one_question` call
# instead of applying a second, ad hoc priority rule.
_PRECEDENCE: tuple[str, ...] = ("reference", "country", "role", "field")

# The two collision-pair members `typo_safety._SEMANTIC_COLLISION_PAIRS`
# names (English, Codex-owned - see config/repair_vocabulary.py's module
# docstring for why this stays English-only rather than gaining an
# unreviewed per-language pair of its own).
_SHIPPING = "shipping"
_SHOPPING = "shopping"
_COLLISION_MEMBERS = (_SHIPPING, _SHOPPING)

_STRIP_CHARS = " .,!?¡¿\"'"


@dataclass(frozen=True)
class Clarification:
    """One localizable clarifying question, not yet rendered to text.

    ``kind`` is the precedence class `one_question` sorts by. ``key`` is the
    message key (``config/conversation_routes.json``, Lane 4) whose
    ``{options}`` placeholder ``options`` fills, joined by the locale's list
    separator when rendered.
    """

    kind: str
    key: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class Repair:
    """One detected self-correction of the reader's own previous turn.

    ``kind`` is ``"market"`` (a directory/target market change - never a
    change to which country's policy governs the answer) or ``"topic"`` (a
    directory-field change, e.g. shipping vs. shopping cost). ``replacement``
    is the corrected value, already in the form a retrieval anchor or a
    rendered clarification option would use. ``replaced`` is the exact span
    of the previous question that was swapped out - ``None`` when that span
    could not be found exactly once, in which case ``rewritten_question`` is
    also ``None`` and the caller should ask, not guess (build a
    :class:`Clarification` instead of rewriting blindly). ``rewritten_question``
    is the previous user question with ``replaced`` swapped for
    ``replacement`` - a standalone question retrieval can be re-run against
    exactly as an explicit follow-up would be.
    """

    kind: str
    replacement: str
    replaced: str | None
    rewritten_question: str | None = None


def one_question(candidates: Sequence[Clarification | None]) -> Clarification | None:
    """Pick at most one :class:`Clarification` by precedence.

    ``reference`` > ``country`` > ``role`` > ``field``. ``None`` entries are
    ignored (a lane that found nothing to ask passes ``None``, not a special
    case the caller must filter out first). Returns ``None`` when every
    candidate is ``None``. An unrecognised ``kind`` sorts last rather than
    raising, so a caller passing a forward-compatible kind this function
    does not yet know about still gets a deterministic (lowest-priority)
    answer instead of an exception.
    """
    present = [candidate for candidate in candidates if candidate is not None]
    if not present:
        return None

    def _rank(candidate: Clarification) -> int:
        try:
            return _PRECEDENCE.index(candidate.kind)
        except ValueError:
            return len(_PRECEDENCE)

    return min(present, key=_rank)


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "").casefold()
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", _fold(value), flags=re.UNICODE))


def _is_collision_ambiguous_token(token: str) -> bool:
    """True when ``token`` plausibly means either collision-pair member.

    An exact match to either member is itself ambiguous with the other:
    "shipping" and "shopping" are one QWERTY-adjacent substitution apart
    (see ``typo_safety._QWERTY_ADJACENCY``), so a reader who typed one
    correctly may still have meant the other. A near-miss (bounded distance
    and typing-slip shape, exactly as ``typo_safety`` itself requires before
    trusting a repair) of either member is ambiguous the same way.
    """
    if token in _COLLISION_MEMBERS:
        return True
    for member in _COLLISION_MEMBERS:
        if token != member and _typo_distance(token, member, 1) <= 1 and _typo_shape_matches(token, member):
            return True
    return False


def typo_clarification(question: str, language: str) -> Clarification | None:
    """Ask once when "shipping" vs. "shopping" cannot be told apart.

    Returns ``None`` (stay silent) when: the question names no token near
    either collision member; the question also contains a disambiguating
    context word in either direction (delivery/courier-leaning or
    purchase/cart-leaning - either settles it, see
    ``config/repair_vocabulary.CONTEXT_DISAMBIGUATION_WORDS``); or the
    language has no configured option labels (fail silent, matching
    ``app/orchestrator/reference_resolution.py``'s "unknown language leaves
    behaviour unchanged" rule).
    """
    language_code = normalize_language_code(language)
    shipping_label = SHIPPING_OPTION_LABEL.get(language_code)
    shopping_label = SHOPPING_OPTION_LABEL.get(language_code)
    if not shipping_label or not shopping_label:
        return None

    tokens = _tokens(question)
    if not tokens:
        return None
    if tokens & CONTEXT_DISAMBIGUATION_WORDS.get(language_code, frozenset()):
        return None
    if not any(_is_collision_ambiguous_token(token) for token in tokens):
        return None

    return Clarification(kind="field", key="clarify_field", options=(shipping_label, shopping_label))


def _strip(value: str) -> str:
    return (value or "").strip(_STRIP_CHARS)


def _count_case_insensitive(text: str, span: str) -> int:
    if not span:
        return 0
    return len(re.findall(re.escape(span), text, flags=re.IGNORECASE))


def _swap_once(text: str, old: str, new: str) -> str:
    return re.sub(re.escape(old), lambda _match: new, text, count=1, flags=re.IGNORECASE)


def _resolve_market_or_topic(text: str, language_code: str) -> tuple[str, str] | None:
    """Resolve a corrected span to a market (via ``services.market_config``
    only - never a locally invented alias) or, failing that, to one of this
    module's small closed topic words.
    """
    candidate = _strip(text)
    if not candidate:
        return None

    codes = find_market_mentions(candidate)
    if len(codes) == 1:
        (code,) = codes
        name = market_display_name(code)
        if name:
            return "market", name

    topic_words = TOPIC_REPLACEMENT_WORDS.get(language_code, {})
    for token in _tokens(candidate):
        member = topic_words.get(token)
        if member == _SHIPPING:
            word = SHIPPING_BARE_WORD.get(language_code)
            if word:
                return "topic", word
        elif member == _SHOPPING:
            word = SHOPPING_BARE_WORD.get(language_code)
            if word:
                return "topic", word
    return None


def _original_span(original: str, folded_match_span: tuple[int, int]) -> str | None:
    """Map a match span found in ``_fold(original)`` back to ``original``.

    Stripping combining marks and casefolding a common Latin accented
    character ("é" -> "e") preserves the character count, so the folded
    string's indices line up with the original's for the accents this
    module's vocabulary actually uses. When that alignment assumption does
    not hold (folding changed the string's length - a rare case such as a
    ligature or German sharp s), this returns ``None`` rather than risk
    slicing the wrong span: a missed repair is safe, a wrong one is not.
    """
    folded = _fold(original)
    if len(folded) != len(original):
        return None
    start, end = folded_match_span
    return original[start:end]


def _find_replaced_span(prior_question: str, kind: str, replacement: str, language_code: str) -> str | None:
    """Find the one span in ``prior_question`` that ``replacement`` corrects.

    Only ever returns a span that occurs in ``prior_question`` EXACTLY once
    and differs from ``replacement`` itself - an ambiguous (zero, or more
    than one) match returns ``None`` so the caller rewrites nothing rather
    than guessing which occurrence was meant.
    """
    candidates: set[str] = set()
    if kind == "market":
        for code in find_market_mentions(prior_question):
            name = market_display_name(code)
            if name and _count_case_insensitive(prior_question, name) == 1:
                candidates.add(name)
    else:
        topic_words = TOPIC_REPLACEMENT_WORDS.get(language_code, {})
        folded_question = _fold(prior_question)
        for stem in topic_words:
            pattern = re.compile(rf"(?<!\w){re.escape(stem)}\w*", re.UNICODE)
            matches = list(pattern.finditer(folded_question))
            if len(matches) != 1:
                continue
            span_text = _original_span(prior_question, matches[0].span())
            if span_text:
                candidates.add(span_text)

    remaining = [candidate for candidate in candidates if candidate.casefold() != replacement.casefold()]
    if len(remaining) == 1:
        return remaining[0]
    return None


def _build_meant_pattern(language_code: str) -> re.Pattern[str] | None:
    cues = MEANT_CUE_PHRASES.get(language_code)
    if not cues:
        return None
    alternation = "|".join(re.escape(cue) for cue in sorted(cues, key=len, reverse=True))
    return re.compile(
        rf"(?:^|[,.;]\s*)(?:\S+[,.]?\s+)?(?:{alternation})\s+(?P<x>.+)$",
        re.IGNORECASE | re.UNICODE,
    )


def _build_contrast_pattern(language_code: str) -> re.Pattern[str] | None:
    not_word = NOT_CUE_WORDS.get(language_code)
    if not not_word:
        return None
    return re.compile(
        rf"(?:^|[,.;]\s*){re.escape(not_word)}\s+(?P<y>.+?),\s*(?P<x>.+)$",
        re.IGNORECASE | re.UNICODE,
    )


def detect_repair(message: str, language: str, prior_user_turns: Sequence[str]) -> Repair | None:
    """Detect a correction of the reader's own previous turn.

    ``prior_user_turns`` is the session's prior USER turns only (oldest
    first, or any order - only the last element is read: a correction always
    targets the immediately preceding question), matching
    ``app.orchestrator.reference_resolution``'s own "assistant turns are
    never a candidate" discipline. Never fires on a message that merely
    starts with a bare negation ("No minimum order?") - both cue patterns
    require one of this module's closed correction phrases
    (``config/repair_vocabulary.MEANT_CUE_PHRASES``) or a full "not Y, X"
    contrast shape with a comma-separated second clause, neither of which a
    bare "No ...?" question matches.
    """
    language_code = normalize_language_code(language)
    text = _strip(message)
    if not text:
        return None
    prior_question = _strip(prior_user_turns[-1]) if prior_user_turns else ""

    contrast_pattern = _build_contrast_pattern(language_code)
    match = contrast_pattern.search(text) if contrast_pattern else None
    if match:
        y = _strip(match.group("y"))
        x = _strip(match.group("x"))
        if y and x and y.casefold() != x.casefold():
            resolved = _resolve_market_or_topic(x, language_code)
            if resolved:
                kind, replacement = resolved
                rewritten = None
                replaced = None
                if prior_question and _count_case_insensitive(prior_question, y) == 1:
                    replaced = y
                    rewritten = _swap_once(prior_question, y, replacement)
                return Repair(kind=kind, replacement=replacement, replaced=replaced, rewritten_question=rewritten)

    meant_pattern = _build_meant_pattern(language_code)
    match = meant_pattern.search(text) if meant_pattern else None
    if match:
        x = _strip(match.group("x"))
        resolved = _resolve_market_or_topic(x, language_code)
        if resolved:
            kind, replacement = resolved
            replaced = None
            rewritten = None
            if prior_question:
                replaced = _find_replaced_span(prior_question, kind, replacement, language_code)
                if replaced:
                    rewritten = _swap_once(prior_question, replaced, replacement)
            return Repair(kind=kind, replacement=replacement, replaced=replaced, rewritten_question=rewritten)

    return None
