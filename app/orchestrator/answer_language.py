"""CX Lane 7 - deterministic answer-language detection (X1, approval 6, option B).

Product decision (2026-09-18, ``docs/conversation-quality/phase2/X1_LANGUAGE_SWITCH_DECISION.md``):
when a user writes in a language other than the widget's selected
``body.language``, the ANSWER follows the message language. Retrieval and
source eligibility keep using the selected language, unchanged - that
distinction (answer language is presentation; ``body.language`` is
authorization) must never blur. This module implements only the detector and
the switch decision; it does not touch retrieval and is not itself wired into
``chat_orchestrator.py`` (single-writer; the coordinator does the wiring).

## Why the marker-word table lives here, self-contained (coordinator review, 2026-09-18)

An earlier revision reused ``config.reference_vocabulary.LOCALIZED_NON_CONTENT_TOKENS``
(9 of the 12 route-copy languages) and copied a small da/ru/sr supplement
from ``chat_orchestrator.py``'s flat, merged ``LOCALIZED_FOLLOW_UP_STOP_WORDS`` /
``LOCALIZED_FOLLOW_UP_FUNCTION_WORDS``. Coordinator review found both sources
too thin for LANGUAGE IDENTIFICATION specifically: they were built (and
reviewed) for a different, narrower purpose - stripping function words from a
short follow-up before asking "is anything left?" (A7/W14) - so each
language's list only covers the handful of words that purpose needed, not
the ~25-40 most frequent closed-class words a language-ID classifier needs
for recall on ordinary customer questions. Reusing them caused real
misdetections (Spanish scored as French, Italian/Finnish/Russian/Swedish/
Serbian questions scored too low to switch at all).

There is therefore nothing reusable in this repository for language
identification specifically (CX_LANES.md's "no duplicated vocabularies" rule
requires reuse only "where none exists" - none does, for this purpose), so
``_RAW_MARKER_WORDS`` below is a purpose-built table, one entry per
``ROUTE_COPY_LANGUAGES`` language, of that language's most frequent
closed-class words: articles, prepositions, pronouns, auxiliary/copula verbs,
question words and conjunctions. It replaces, rather than duplicates, the
narrower table this module used before; it does not touch or copy
``chat_orchestrator.py``'s own tables, which remain scoped to their own W14/A7
purpose.

## Overlap weighting (coordinator review: "de", "en", "la", "a", "i", "e",
## "que" must not flip the winner)

Many closed-class words are near-identical across related languages by
etymology ("la" in es/fr/it, "de" in nl/es/fr, "que" in es/fr, "en" in
fr/nl). Hand-picking which of these to exclude is fragile and does not
scale to 12 languages. Instead every word's weight is derived automatically
from how many of the 12 languages' lists contain it (see
``_word_overlap_weight``): a word unique to one language counts fully; a
word shared by two counts at half; by three, less; by four or more, barely
at all. This makes the overlap penalty data-driven and self-maintaining as
the table grows, rather than a per-word judgement call.

## Script and diacritic evidence (coordinator review: recall was too low from
## word-counting alone on real customer sentences, which contain few function
## words relative to content words)

Beyond marker words, the detector also credits language-distinctive
characters actually present in the raw message (before accent-stripping):
Spanish n-with-tilde/inverted punctuation, German sharp s, French cedilla/
oe-ligature/circumflex vowels, Nordic ae/oe/aa letters, Swedish/Finnish
umlauts, Russian-only Cyrillic letters (not shared with Serbian Cyrillic),
and Serbian-only letters in either script. Italian is additionally credited
for a word-final accented vowel (a positional pattern, not a bare
character, because the plain vowels overlap with French); Finnish for its
characteristic doubled-vowel spelling; Serbian for the idiomatic "da li"
yes/no-question opener. See ``_DISTINCTIVE_STRONG``, ``_DISTINCTIVE_MODERATE``
and the position/pattern checks below for exactly what each language is
credited for and why.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

# The 12 route-copy languages (config/conversation_routes.json's "locales"
# keys) - the only languages `resolve_answer_language` may switch into, per
# the X1 decision ("switch ... into a language that has route copy").
ROUTE_COPY_LANGUAGES: tuple[str, ...] = ("da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "ru", "sr", "sv")

# --- Marker words (closed-class only): ~25-40 per language -----------------
# Articles, prepositions, pronouns, auxiliary/copula verbs, question words
# and conjunctions - the most frequent members of each closed grammatical
# class. Written as plain space-separated strings (one token each);
# normalization (NFKD-strip accents, casefold) is applied uniformly when the
# lookup table is built, so an entry may be typed with or without its native
# accent. Serbian is listed in both scripts because the language is written
# in either.
_RAW_MARKER_WORDS: dict[str, str] = {
    "en": (
        "the a an of to in on at is are was were be been do does did "
        "and or but this that these those what how where when why who which "
        "you your we our my it its not for with"
    ),
    "de": (
        "der die das den dem ein eine einer und oder aber ist sind war waren "
        "ich du er sie wir ihr mein dein was wie wo wann warum wer welche "
        "nicht fuer mit auf zu von"
    ),
    "fr": (
        "le la les un une des du et ou mais est sont etait je tu il elle nous "
        "vous ils mon ma que qui quoi ou quand pourquoi comment combien pas "
        "pour avec dans de"
    ),
    "es": (
        "el la los las un una y o pero es son era yo tu el ella nosotros "
        "vosotros mi que quien donde cuando como cuanto no para con en de hay"
    ),
    "it": (
        "il lo la i gli le un uno una e o ma e sono era io tu lui lei noi voi "
        "mio tuo che chi dove quando perche come quanto non per con in di"
    ),
    "nl": (
        "de het een en of maar is zijn was waren ik jij hij zij wij jullie "
        "mijn jouw wat hoe waar wanneer waarom wie welke niet voor met op van "
        "naar"
    ),
    "sv": (
        "den det en ett och eller men ar var jag du han hon vi ni min din vad "
        "hur nar varfor vem vilken inte for med pa av till"
    ),
    "no": (
        "den det en ei et og eller men er var jeg du han hun vi dere min din "
        "hva hvordan hvor nar hvorfor hvem hvilken ikke for med pa av til"
    ),
    "da": (
        "den det en et og eller men er var jeg du han hun vi jer min din hvad "
        "hvordan hvor hvornar hvorfor hvem hvilken ikke for med pa af til"
    ),
    "fi": (
        "se ne ja tai mutta on ovat oli mina sina han me te he minun sinun "
        "mika mita miten missa milloin miksi kuka kuinka ei varten kanssa onko "
        "voinko paljonko"
    ),
    "ru": (
        "и или но а что это тот я ты он она мы вы они мой твой как где когда "
        "почему кто какой какая какое сколько не для с со на в во по к у от "
        "до из при ли же есть был была было были"
    ),
    "sr": (
        "i ili ali je su bio bila ja ti on ona mi vi oni moj tvoj sta kako "
        "gde kada zasto ko koji koliko ne za sa u na da li "
        "и или али је су био била ја ти он она ми ви они мој твој шта како "
        "где када зашто ко који колико не за са у на да ли"
    ),
}


def _unaccented(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _normalize_marker(word: str) -> str:
    return _unaccented(word or "").casefold().strip()


def _word_overlap_weight(language_count: int) -> float:
    """How much a marker word counts toward its language's score, based on
    how many of the 12 languages' lists contain the SAME normalized word.
    Unique to one language: full weight. Shared: progressively discounted,
    so a word such as "la" (es/fr/it) or "de" (nl/es/fr) can never by itself
    flip which language wins - see module docstring."""
    if language_count <= 1:
        return 1.0
    if language_count == 2:
        return 0.5
    if language_count == 3:
        return 0.3
    return 0.2


def _build_word_weights() -> dict[str, dict[str, float]]:
    per_language: dict[str, frozenset[str]] = {
        language: frozenset(_normalize_marker(word) for word in raw.split())
        for language, raw in _RAW_MARKER_WORDS.items()
    }
    overlap_counts: dict[str, int] = {}
    for words in per_language.values():
        for word in words:
            overlap_counts[word] = overlap_counts.get(word, 0) + 1
    weights: dict[str, dict[str, float]] = {}
    for language, words in per_language.items():
        weights[language] = {word: _word_overlap_weight(overlap_counts[word]) for word in words}
    return weights


# language -> {normalized marker word: overlap-discounted weight}
MARKER_WORD_WEIGHTS: dict[str, dict[str, float]] = _build_word_weights()

# --- Distinctive-character evidence -----------------------------------------
# Characters checked against the RAW message (accents intact), because
# accent-stripping is exactly what would erase this signal. Each set lists
# characters that are rare-to-absent in the OTHER route-copy languages, so a
# single occurrence is meaningful; only distinct character TYPES present are
# counted (not occurrences), so one repeated letter cannot inflate the score.
_DISTINCTIVE_STRONG: dict[str, frozenset[str]] = {
    "es": frozenset("ñÑ¿¡"),
    "de": frozenset("ß"),
    "fr": frozenset("çÇœŒâêîôûÂÊÎÔÛ"),
    "ru": frozenset("ыэъёЫЭЪЁ"),  # Cyrillic letters Serbian's alphabet does not have
    "sr": frozenset("đšžčćĐŠŽČĆђјљњћџЂЈЉЊЋЏ"),  # Latin+Cyrillic letters unique to Serbian here
}
_DISTINCTIVE_MODERATE: dict[str, frozenset[str]] = {
    "es": frozenset("áéíóúÁÉÍÓÚ"),
    "de": frozenset("äöüÄÖÜ"),
    "fr": frozenset("àèùÀÈÙ"),
    "no": frozenset("æøåÆØÅ"),
    "da": frozenset("æøåÆØÅ"),  # identical to "no" - see resolve_answer_language's near-pair note
    "sv": frozenset("åäöÅÄÖ"),
    "fi": frozenset("äöÄÖ"),
}
_STRONG_CHAR_WEIGHT = 3.0
_MODERATE_CHAR_WEIGHT = 1.5

# Italian: a plain accented vowel (a/e/i/o/u with grave) overlaps with
# French, so only a WORD-FINAL accented vowel is credited - Italian's own
# distinguishing position ("citta", "perche", "cosi", "pero").
_ITALIAN_WORD_FINAL_ACCENT = re.compile(r"[a-zA-Z]+[àèìòù]\b")
_ITALIAN_FINAL_ACCENT_WEIGHT = 2.0

# Finnish: characteristic doubled-vowel spelling (long vowels are written as
# a doubled letter - "maksaa", "Suomeen", "saapuu"). Weak on its own (short
# doubled runs can occur elsewhere) but a useful additional signal alongside
# Finnish's very distinct question-word vocabulary.
_FINNISH_DOUBLE_VOWEL = re.compile(r"(?i)([aeiouyäö])\1")
_FINNISH_DOUBLE_VOWEL_WEIGHT = 1.0
_FINNISH_DOUBLE_VOWEL_MAX_CREDITS = 2

# Serbian: the idiomatic yes/no-question opener "da li" (either script),
# distinct from a bare "da"/"li" collision with other languages' function
# words.
_SERBIAN_DA_LI = re.compile(r"(?i)\bda li\b|\bда ли\b")
_SERBIAN_DA_LI_WEIGHT = 2.0


def _distinctive_bonus(language: str, raw_message: str) -> float:
    bonus = 0.0
    strong = _DISTINCTIVE_STRONG.get(language)
    if strong:
        bonus += _STRONG_CHAR_WEIGHT * sum(1 for char in strong if char in raw_message)
    moderate = _DISTINCTIVE_MODERATE.get(language)
    if moderate:
        bonus += _MODERATE_CHAR_WEIGHT * sum(1 for char in moderate if char in raw_message)
    if language == "it":
        matches = len(_ITALIAN_WORD_FINAL_ACCENT.findall(raw_message))
        bonus += _ITALIAN_FINAL_ACCENT_WEIGHT * min(matches, 2)
    if language == "fi":
        matches = len(_FINNISH_DOUBLE_VOWEL.findall(raw_message))
        bonus += _FINNISH_DOUBLE_VOWEL_WEIGHT * min(matches, _FINNISH_DOUBLE_VOWEL_MAX_CREDITS)
    if language == "sr" and _SERBIAN_DA_LI.search(raw_message):
        bonus += _SERBIAN_DA_LI_WEIGHT
    return bonus


# A tokenizer that returns letter-only words (Unicode-aware; digits and
# punctuation are never tokens), normalized the same way as the marker
# tables, so a numeric/code-only message tokenizes to nothing and can never
# contribute a marker hit or count toward MIN_TOKENS.
_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)

_CYRILLIC_PATTERN = re.compile(r"[Ѐ-ӿ]")
_LATIN_PATTERN = re.compile(r"[A-Za-zÀ-ɏ]")

_CYRILLIC_ONLY_LANGUAGES = frozenset({"ru"})
_NEAR_LANGUAGE_GROUP = frozenset({"no", "da", "sv"})


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
    ``score`` is its weighted evidence total (marker-word overlap weights
    plus distinctive-character/pattern bonuses); ``runner_up`` is the
    next-highest candidate's score (0.0 when there is no other candidate).
    ``reason`` documents which branch produced the result.
    """

    language: str | None
    score: float
    runner_up: float
    reason: str


def detect_message_language(
    message: str,
    *,
    candidates: tuple[str, ...] = ROUTE_COPY_LANGUAGES,
) -> Detection:
    """Deterministically score ``message`` against each of ``candidates`` by
    combining overlap-weighted marker-word hits with distinctive-character
    evidence (see module docstring). Pure and order-independent: the same
    message and candidate set always produce the same result, using only
    fixed vocabulary lookups, regexes and arithmetic - no model call, no
    network, no per-run state.
    """
    script = _script_signal(message)
    if script == "mixed":
        return Detection(None, 0.0, 0.0, "mixed_script")
    if script == "none":
        return Detection(None, 0.0, 0.0, "no_letters")

    if script == "cyrillic":
        eligible = tuple(language for language in candidates if language in {"ru", "sr"})
    else:
        eligible = tuple(language for language in candidates if language not in _CYRILLIC_ONLY_LANGUAGES)

    tokens = _tokenize(message)
    if not tokens:
        return Detection(None, 0.0, 0.0, "no_tokens")

    scores: dict[str, float] = {}
    for language in eligible:
        weights = MARKER_WORD_WEIGHTS.get(language, {})
        word_score = sum(weights.get(token, 0.0) for token in tokens)
        scores[language] = word_score + _distinctive_bonus(language, message)

    if not scores:
        return Detection(None, 0.0, 0.0, "no_eligible_candidates")

    ordered = sorted(scores.items(), key=lambda item: (-item[1], candidates.index(item[0])))
    top_language, top_score = ordered[0]
    runner_up_score = ordered[1][1] if len(ordered) > 1 else 0.0

    if top_score <= 0:
        return Detection(None, 0.0, runner_up_score, "no_marker_hits")

    return Detection(top_language, top_score, runner_up_score, "scored")


# --- Switch thresholds (documented; tuned against the Lane 7 acceptance set
# in tests/unit/test_cx_answer_language.py, not individual probes) ----------
MIN_TOKENS = 4          # at least 4 word tokens in the message

# Latin-script candidates: overlap-weighted word evidence plus diacritic
# bonuses must clear this floor, ahead by at least MIN_MARGIN over the
# runner-up.
MIN_SCORE = 1.5
MIN_MARGIN = 1.0

# Closely related language pairs need a bigger margin before switching
# between them, because their function words overlap heavily (Danish,
# Norwegian and Swedish share cognate connectors, and da/no share the same
# distinctive letters ae/oe/aa outright - see _DISTINCTIVE_MODERATE).
_NEAR_PAIR_EXTRA_MARGIN = 1.5

# Serbian Latin shares short function words with unrelated Latin-script
# languages by coincidence more than most pairs here; require extra margin
# whenever Serbian is the candidate winning against any other candidate.
_SERBIAN_EXTRA_MARGIN = 1.5

# Cyrillic-script messages: ru and sr are the only eligible candidates (see
# detect_message_language), so the false-positive risk that justifies the
# higher Latin-script floor (many languages' function words overlapping)
# does not apply the same way - the real risk is ru/sr confusion, which the
# distinctive-letter evidence (_DISTINCTIVE_STRONG) is built to resolve. A
# Cyrillic message with any Russian-only-letter or Russian-function-word
# evidence, and no Serbian evidence at all, switches to Russian even on a
# thin score - this is what lets short, mostly-content-word Russian customer
# questions (few closed-class words relative to their length) still switch,
# per coordinator review 2026-09-18.
CYRILLIC_MIN_SCORE = 0.5
CYRILLIC_MIN_MARGIN = 0.5
CYRILLIC_SERBIAN_EXTRA_MARGIN = 1.5


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

    script = _script_signal(message)
    margin = detection.score - detection.runner_up

    if script == "cyrillic":
        required_score = CYRILLIC_MIN_SCORE
        required_margin = CYRILLIC_MIN_MARGIN
        if detection.language == "sr":
            required_margin += CYRILLIC_SERBIAN_EXTRA_MARGIN
    else:
        required_score = MIN_SCORE
        required_margin = MIN_MARGIN
        if frozenset({detection.language, selected_language}) <= _NEAR_LANGUAGE_GROUP:
            required_margin += _NEAR_PAIR_EXTRA_MARGIN
        if detection.language == "sr":
            required_margin += _SERBIAN_EXTRA_MARGIN

    if detection.score < required_score or margin < required_margin:
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
