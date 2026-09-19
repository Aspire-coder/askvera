"""CX Lane 7 - deterministic answer-language detection (X1, approval 6, option B).

Product decision (2026-09-18, ``docs/conversation-quality/phase2/X1_LANGUAGE_SWITCH_DECISION.md``):
when a user writes in a language other than the widget's selected
``body.language``, the ANSWER follows the message language. Retrieval and
source eligibility keep using the selected language, unchanged - that
distinction (answer language is presentation; ``body.language`` is
authorization) must never blur. This module implements only the detector and
the switch decision; it does not touch retrieval and is not itself wired into
``chat_orchestrator.py`` (single-writer; the coordinator does the wiring).

## Where the marker words come from (CX_LANES.md: "no duplicated vocabularies")

``MARKER_WORDS`` below is a per-language table of closed-class function words
(articles, prepositions, conjunctions, WH-question words, pronouns, copulas)
used to *count*, not to interpret, how much of a message looks like each
candidate language. Two sources already exist in this repository for exactly
this closed grammatical class:

1. ``config.reference_vocabulary.LOCALIZED_NON_CONTENT_TOKENS`` - already
   reviewed, already accent-stripped and casefolded, keyed by language code.
   It covers en, fr, de, nl, it, es, fi, sv, no directly (its ``pt`` entry is
   not a route-copy language here and is left out). Reused verbatim.
2. ``app/orchestrator/chat_orchestrator.py``'s ``LOCALIZED_FOLLOW_UP_STOP_WORDS``
   and ``LOCALIZED_FOLLOW_UP_FUNCTION_WORDS`` cover the same closed classes for
   every conversation language, including da, ru and sr - but both are built
   (via ``_follow_up_token_set``) as ONE FLAT merged set for a different
   purpose (stripping any function word before asking "is anything left?"),
   not as a dict keyed by language, so they cannot be imported and used for
   per-language counting directly. Importing them would also create a import
   cycle once the coordinator wires this module into ``chat_orchestrator.py``.

Route-copy languages missing from source 1 (da, ru, sr) get a SMALL,
literal supplement table below. It is not invented: every token is copied
from the exact per-language line already reviewed in
``chat_orchestrator.py`` for da/no ("for til og" plus the da-only WH/pronoun
line), ru (the Cyrillic function-word and WH/pronoun lines) and sr (the
Latin and Cyrillic WH/pronoun lines, plus "u za sa" / "у за са"), whose
per-language order is confirmed by that file's own dict,
``LOCALIZED_TOPIC_SHIFT_OPENERS`` (keyed nl, fr, de, es, pt, it, sv, da, no,
fi, ru, sr - the same order the flat merges were built in). Every token
copied is a closed-class word (article/preposition/conjunction/WH-word/
pronoun/copula) in the language it is keyed under here, matching the
"closed-class only" discipline ``config/alias_function_word_guard.py``
already documents for the same underlying tables.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

from config.reference_vocabulary import LOCALIZED_NON_CONTENT_TOKENS

# The 12 route-copy languages (config/conversation_routes.json's "locales"
# keys) - the only languages `resolve_answer_language` may switch into, per
# the X1 decision ("switch ... into a language that has route copy").
ROUTE_COPY_LANGUAGES: tuple[str, ...] = ("da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "ru", "sr", "sv")

_CYRILLIC_ONLY_LANGUAGES = frozenset({"ru"})
_NEAR_LANGUAGE_GROUP = frozenset({"no", "da", "sv"})


def _unaccented(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _normalize_marker(word: str) -> str:
    """Fold a marker/token the same way (NFKD-strip accents, casefold) so a
    reused, already-stripped vocabulary entry and a hand-typed supplement
    entry compare equal, and so an accented incoming token matches either."""
    return _unaccented(word or "").casefold().strip()


# --- Supplement: da, ru, sr only (see module docstring for provenance) -----
_SUPPLEMENTARY_MARKER_WORDS: dict[str, frozenset[str]] = {
    # Danish. WH/pronoun line + the da/no-shared connector line, both copied
    # verbatim from chat_orchestrator.LOCALIZED_FOLLOW_UP_STOP_WORDS /
    # LOCALIZED_FOLLOW_UP_FUNCTION_WORDS's da-ordered slices, plus "med" and
    # "saa" from LOCALIZED_TOPIC_SHIFT_OPENERS["da"] ("hvad med", "hvad saa med").
    "da": frozenset({
        "hvem", "hvad", "hvor", "hvornar", "hvorfor", "hvordan", "hvilken", "hvilket", "hvilke",
        "jer", "os", "jeg", "vi", "for", "til", "og", "med", "sa",
    }),
    # Russian. WH/pronoun line + function-word line, both copied verbatim
    # from the same two tables' ru-ordered slices (Cyrillic), plus "насчёт"
    # from LOCALIZED_TOPIC_SHIFT_OPENERS["ru"]. Normalized (accent-stripped,
    # casefolded) below like every other entry - Cyrillic has no combining
    # accents here, so normalization only casefolds.
    "ru": frozenset({
        "что", "чего", "чем", "кто", "кого", "кому", "как", "где", "куда", "когда", "почему",
        "зачем", "сколько", "какой", "какая", "какие", "чей", "потом", "тогда",
        "ты", "вы", "тебя", "вас", "тобой", "вами", "я", "мне", "меня", "нас",
        "в", "во", "для", "по", "на", "с", "со", "и", "а", "насчет",
    }),
    # Serbian. Both scripts (sr is written in either) - WH/pronoun and
    # function-word lines copied verbatim from the same two tables' sr-Latin
    # and sr-Cyrillic slices, plus the "šta je sa" / "шта је са" opener stems.
    "sr": frozenset({
        "sta", "sto", "ko", "koga", "kome", "kako", "gde", "gdje", "kada", "kad", "zasto",
        "koliko", "koji", "koja", "koje", "onda", "ti", "vi", "tebe", "vas", "tobom", "vama",
        "ja", "mi", "mnom", "nama", "u", "za", "sa", "je",
        "шта", "што", "ко", "кога", "коме", "како", "где", "када", "зашто", "колико",
        "који", "која", "које", "онда", "ти", "ви", "тебе", "вас", "тобом", "вама",
        "ја", "ми", "мном", "нама", "у", "за", "са", "је",
    }),
}


def _build_marker_words() -> dict[str, frozenset[str]]:
    words: dict[str, frozenset[str]] = {}
    for language in ROUTE_COPY_LANGUAGES:
        if language in LOCALIZED_NON_CONTENT_TOKENS:
            source = LOCALIZED_NON_CONTENT_TOKENS[language]
        elif language in _SUPPLEMENTARY_MARKER_WORDS:
            source = _SUPPLEMENTARY_MARKER_WORDS[language]
        else:  # pragma: no cover - defensive; every route-copy language is covered above
            source = frozenset()
        words[language] = frozenset(_normalize_marker(token) for token in source)
    return words


# Per-language closed-class marker table, one frozenset per ROUTE_COPY_LANGUAGES
# entry. Built once at import time; every entry is already normalized.
MARKER_WORDS: dict[str, frozenset[str]] = _build_marker_words()

# A tokenizer that returns letter-only words (Unicode-aware; digits and
# punctuation are never tokens), normalized the same way as MARKER_WORDS, so
# a numeric/code-only message tokenizes to nothing and can never contribute a
# marker hit or count toward MIN_TOKENS.
_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)

_CYRILLIC_PATTERN = re.compile(r"[Ѐ-ӿ]")
_LATIN_PATTERN = re.compile(r"[A-Za-zÀ-ɏ]")


def _tokenize(message: str) -> tuple[str, ...]:
    normalized = _unaccented(message or "").casefold()
    return tuple(_WORD_PATTERN.findall(normalized))


def _script_signal(message: str) -> str:
    """Classify the message's letters as "cyrillic", "latin", "mixed" (both
    present - ambiguous per the X1 decision) or "none" (no letters at all,
    e.g. a numeric/code-only message)."""
    text = message or ""
    has_cyrillic = bool(_CYRILLIC_PATTERN.search(text))
    has_latin = bool(_LATIN_PATTERN.search(text))
    if has_cyrillic and has_latin:
        return "mixed"
    if has_cyrillic:
        return "cyrillic"
    if has_latin:
        return "latin"
    return "none"


class Detection(NamedTuple):
    """Deterministic scoring result of `detect_message_language`.

    ``language`` is the top-scoring candidate (None when no candidate scored
    above zero, the script was mixed, or the message had no letters at all).
    ``score`` is its marker-hit count; ``runner_up`` is the next-highest
    candidate's marker-hit count (0 when there is no other candidate).
    ``reason`` documents which branch produced the result.
    """

    language: str | None
    score: int
    runner_up: int
    reason: str


def detect_message_language(
    message: str,
    *,
    candidates: tuple[str, ...] = ROUTE_COPY_LANGUAGES,
) -> Detection:
    """Deterministically score ``message`` against each of ``candidates`` by
    counting closed-class marker-word hits (see ``MARKER_WORDS``). Pure and
    order-independent: the same message and candidate set always produce the
    same result, using only fixed vocabulary lookups and arithmetic - no
    model call, no network, no per-run state.
    """
    script = _script_signal(message)
    if script == "mixed":
        return Detection(None, 0, 0, "mixed_script")
    if script == "none":
        return Detection(None, 0, 0, "no_letters")

    if script == "cyrillic":
        eligible = tuple(language for language in candidates if language in {"ru", "sr"})
    else:
        eligible = tuple(language for language in candidates if language not in _CYRILLIC_ONLY_LANGUAGES)

    tokens = _tokenize(message)
    if not tokens:
        return Detection(None, 0, 0, "no_tokens")

    scores: dict[str, int] = {}
    for language in eligible:
        markers = MARKER_WORDS.get(language, frozenset())
        scores[language] = sum(1 for token in tokens if token in markers)

    if not scores:
        return Detection(None, 0, 0, "no_eligible_candidates")

    ordered = sorted(scores.items(), key=lambda item: (-item[1], candidates.index(item[0])))
    top_language, top_score = ordered[0]
    runner_up_score = ordered[1][1] if len(ordered) > 1 else 0

    if top_score <= 0:
        return Detection(None, 0, runner_up_score, "no_marker_hits")

    return Detection(top_language, top_score, runner_up_score, "scored")


# --- Switch thresholds (documented; deliberately conservative) -------------
# A strong, unambiguous signal requires ALL three:
MIN_MARKER_HITS = 3   # at least 3 marker-word hits for the winning language
MIN_MARGIN = 2         # at least a 2-hit margin over the runner-up
MIN_TOKENS = 4         # at least 4 word tokens in the message

# Closely related language pairs need a bigger margin before switching
# between them, because their function words overlap heavily (Danish,
# Norwegian and Swedish share "og"/"og"/"och" cognates, "for", "til"/"till",
# etc.). One extra hit of margin on top of MIN_MARGIN.
_NEAR_PAIR_EXTRA_MARGIN = 2

# Serbian is written in two scripts; its Latin form shares many short
# function words with other Latin-script candidates by coincidence (e.g.
# "ja" - Serbian "I" - collides with German/Scandinavian "ja"/yes-shaped
# tokens in casual text). Require extra margin whenever Serbian is the
# candidate winning against ANY other candidate.
_SERBIAN_EXTRA_MARGIN = 2


class AnswerLanguage(NamedTuple):
    """The presentation-language decision for one turn.

    ``answer_language`` drives the prompt's user-language line, the
    localized copy and the post-processing vocabularies (see module
    docstring). ``switched`` is True only when it differs from
    ``selected_language``. ``reason`` documents which branch decided.
    """

    answer_language: str
    switched: bool
    reason: str


def resolve_answer_language(message: str, selected_language: str) -> AnswerLanguage:
    """Decide the answer language for one turn. Switches away from
    ``selected_language`` ONLY on a strong, unambiguous signal, per the X1
    decision: never on a single-word or very short message, never on a
    numbers/codes-only message, never when the message's detected language
    already matches the selection, and only into a route-copy language.
    """
    tokens = _tokenize(message)
    if len(tokens) < MIN_TOKENS:
        return AnswerLanguage(selected_language, False, "too_short")

    detection = detect_message_language(message, candidates=ROUTE_COPY_LANGUAGES)
    if detection.language is None:
        return AnswerLanguage(selected_language, False, detection.reason)

    if detection.language == selected_language:
        return AnswerLanguage(selected_language, False, "matches_selected")

    if detection.language not in ROUTE_COPY_LANGUAGES:
        return AnswerLanguage(selected_language, False, "no_route_copy")  # pragma: no cover - defensive

    required_margin = MIN_MARGIN
    if frozenset({detection.language, selected_language}) <= _NEAR_LANGUAGE_GROUP:
        required_margin += _NEAR_PAIR_EXTRA_MARGIN
    if detection.language == "sr":
        required_margin += _SERBIAN_EXTRA_MARGIN

    margin = detection.score - detection.runner_up
    if detection.score < MIN_MARKER_HITS or margin < required_margin:
        return AnswerLanguage(selected_language, False, "below_threshold")

    return AnswerLanguage(detection.language, True, "strong_signal")


def retrieval_language(selected_language: str, answer_language: str) -> str:
    """Invariant helper (explicit, greppable no-op): retrieval and source
    eligibility ALWAYS use the selected widget language, never the detected
    answer language, regardless of whether a switch happened. ``answer_language``
    is accepted (not `_`-prefixed away) so a test can assert this function's
    return value never depends on it - the eligibility invariant the X1
    decision requires ("Retrieval (item 4) keeps body.language").
    """
    return selected_language
