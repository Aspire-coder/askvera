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
from functools import lru_cache
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
        # "fur" (not "fuer") - matches the accent-stripped normalized form
        # of "für"; "fuer" as literally spelled never matched anything,
        # since "für" normalizes via NFKD-strip to "fur", not "fuer" - a
        # real bug found while tuning the Fable CX re-review word-evidence
        # gate, which made this collision-free word's absence newly costly.
        "nicht fur mit auf zu von werden"
    ),
    "fr": (
        "le la les un une des du et ou mais est sont etait je tu il elle nous "
        "vous ils mon ma que qui quoi ou quand pourquoi comment combien pas "
        "pour avec dans de au aux par quel quels quelle quelles ce cette ces"
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
        "voinko voin jonka paljonko"
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

# Every normalized word that is a recognized marker for ANY language -
# used only to make sure the capitalized-proper-noun heuristic below never
# masks a genuine, capitalized closed-class word ("Quel", "Wie", "Was" at a
# sentence's start).
ALL_MARKER_WORDS: frozenset[str] = frozenset(
    word for weights in MARKER_WORD_WEIGHTS.values() for word in weights
)

# --- "None of the above" SINK languages (Fable CX review finding F1, ------
# 2026-09-19) --------------------------------------------------------------
# Reachable TODAY: every non-route market's widget still sends "en" (the
# other 27 configured languages aren't in ChatRequest's enum), so a message
# actually written in one of them arrives on an "en" widget - exactly the
# case the F1 probes exercise. The winner-share gate (below) cannot fix
# this alone: Portuguese and Spanish share enough real function words that
# a genuinely Portuguese sentence can score "es" with a perfectly healthy
# winner_share, because from the detector's perspective those words ARE
# Spanish - it has no Portuguese model to compare against.
#
# The fix is to give it one: a small closed marker table (function words +
# distinctive letters), one entry per likely non-route language, scored
# ALONGSIDE the 12 real candidates by the exact same mechanism - but a sink
# language can never itself become ``answer_language``. If a sink's score
# rivals or beats the route winner's, or a sink's distinctive letter is
# anywhere in the message, that is itself the signal: the message probably
# ISN'T written in any of the 12, so the safest answer is not to switch at
# all (reason "non_route_language_likely") - never a guess at which of the
# 12 relatives it might be.
#
# Not exhaustive (config/markets.json configures languages beyond this
# list, e.g. ar/el/et/he/ka/ku/kz/ky/lt/lv/uz), but these are the languages
# Fable's review found actually colliding with a route-copy language's
# vocabulary; the rest already fail closed today via the winner-share gate
# and the selected-language gate (S4) - a sink is an extra safety net for
# the specific collisions found, not a claim of covering every non-route
# language there is.
_SINK_LANGUAGES: tuple[str, ...] = ("pt", "hu", "ro", "pl", "cs", "sk", "tr", "hr", "bs", "sq", "mk", "bg", "uk")

# Cyrillic-script sinks (checked only against a Cyrillic-script message);
# every other sink above is Latin-script.
_CYRILLIC_SINK_LANGUAGES: frozenset[str] = frozenset({"mk", "bg", "uk"})

_SINK_RAW_MARKER_WORDS: dict[str, str] = {
    # Portuguese: coordinator-supplied word list verbatim.
    "pt": "nao sao voce os das dos uma um o com qual para que",
    "hu": "a az es hogy nem milyen mi hogyan",
    "ro": "si un o sunt este cu pentru ce cum unde cand nu",
    "pl": "i nie jest sa na do z co jak ale",
    "cs": "a je jsou na co jak pro ale",
    "sk": "a je su na co ako pre ale",
    "tr": "ve bir bu ne icin mi nasil ile",
    # Croatian/Bosnian: essentially the same closed-class vocabulary as
    # Latin Serbian (they are the same pluricentric language for this
    # purpose - see _SERBIAN_EXTRA_MARGIN's own note), which is exactly
    # why they need to be a sink against "sr" specifically: the same
    # evidence that scores "sr" scores these too, so it must never be
    # treated as proof the message IS Serbian rather than one of these.
    "hr": "i ili ali je su bio bila ja ti on ona mi vi oni moj tvoj sta kako gde kada zasto ko koji koliko ne za sa u na tko gdje",
    "bs": "i ili ali je su bio bila ja ti on ona mi vi oni moj tvoj sta kako gdje kada zasto ko koji koliko ne za sa u na",
    "sq": "dhe eshte nuk kjo kush sa si per ku kur",
    "mk": "и или но а што е се на за како кој која кое колку не со од да го",
    "bg": "и или но а какво е на за с кой коя кое колко не със този",
    "uk": "і або але а що це як на для з цей ця це не зі",
}

_SINK_DISTINCTIVE_STRONG: dict[str, frozenset[str]] = {
    # NOTE: adding Spanish's own accented vowels (á/í/ó/ú) here was tried
    # and reverted - Portuguese and Spanish share that whole accent
    # inventory closely enough (both Iberian Romance) that crediting it to
    # the sink vetoed genuinely Spanish sentences too, not just the
    # Portuguese false positives. Portuguese is distinguished from Spanish
    # by its own exclusive letters and marker words only; some genuinely
    # Portuguese sentences with no ã/õ/ç and thin word overlap remain a
    # documented miss (see CX_LANE7_ANSWER_LANGUAGE.md).
    "pt": frozenset("ãõçÃÕÇ"),
    "hu": frozenset("őűŐŰ"),
    "ro": frozenset("ășțâîĂȘȚÂÎ"),
    "pl": frozenset("ąęłńśźżĄĘŁŃŚŹŻ"),
    "cs": frozenset("ěřůťďĚŘŮŤĎ"),
    "sk": frozenset("ľĺĽĹěťďĚŤĎ"),
    "tr": frozenset("ğşıİĞŞ"),
    "hr": frozenset("đĐ"),
    "bs": frozenset("đĐ"),
    "sq": frozenset("ëË"),
    "mk": frozenset("ѓќѕЃЌЅ"),
    "uk": frozenset("іїєґІЇЄҐ"),
    # Bulgarian has no letter that is reliably exclusive to it among these
    # candidates; see _BULGARIAN_MEDIAL_YER below for its own, positional
    # signal instead (coordinator: "'ъ' in word-medial position is
    # bg-typical").
}

# Every sink language's distinctive letters, flattened into one set, for the
# blanket veto in resolve_answer_language ("distinctive letters of a sink
# present -> no switch") - deliberately unconditional and independent of
# which sink they belong to, since the point is only "this doesn't look
# like any of the 12".
_ALL_SINK_DISTINCTIVE_LETTERS: frozenset[str] = frozenset(
    character for letters in _SINK_DISTINCTIVE_STRONG.values() for character in letters
)

# Bulgarian's "ъ" (yer) is an ordinary, frequent VOWEL sitting between two
# consonants within a word ("България", "мъж", "връзка") - unlike Russian,
# where "ъ" only ever appears as a separator sign directly after a prefix
# and before an iotated vowel (е/ё/ю/я), e.g. "объект", "подъезд". Matching
# "a Cyrillic consonant, ъ, a Cyrillic consonant" (never followed by one of
# the four iotated vowels, which would instead point to the Russian
# separator-sign pattern) is a reasonable, if imperfect, proxy for the
# Bulgarian shape; an occasional Russian false match only ever makes the
# sink veto fire when it need not (the safe direction - see module
# docstring on sinks above).
_BULGARIAN_MEDIAL_YER = re.compile(
    r"(?i)[бвгджзйклмнпрстфхцчшщ]ъ[бвгджзйклмнпрстфхцчшщ](?![еёюя])"
)
_BULGARIAN_MEDIAL_YER_WEIGHT = 2.0
_BULGARIAN_MEDIAL_YER_MAX_CREDITS = 2


def _build_sink_word_weights() -> dict[str, dict[str, float]]:
    """Same overlap-discount mechanism as ``_build_word_weights``, but scoped
    to the sink table alone - a word shared between two SINKS (e.g. "je"
    between cs/sk) is discounted the same way; a sink word that also happens
    to be a route-copy marker word is NOT discounted against the route
    table, because sinks are never compared against each other for identity,
    only used as a veto against a route winner (see module docstring)."""
    per_language: dict[str, frozenset[str]] = {
        language: frozenset(_normalize_marker(word) for word in raw.split())
        for language, raw in _SINK_RAW_MARKER_WORDS.items()
    }
    overlap_counts: dict[str, int] = {}
    for words in per_language.values():
        for word in words:
            overlap_counts[word] = overlap_counts.get(word, 0) + 1
    weights: dict[str, dict[str, float]] = {}
    for language, words in per_language.items():
        weights[language] = {word: _word_overlap_weight(overlap_counts[word]) for word in words}
    return weights


SINK_MARKER_WORD_WEIGHTS: dict[str, dict[str, float]] = _build_sink_word_weights()

# Every normalized word that is a recognized marker for ANY sink language -
# used the same way ALL_MARKER_WORDS is: so the capitalized-proper-noun
# heuristic in _mask_non_signal_spans never masks a genuine, capitalized
# closed-class SINK word either (e.g. Portuguese "Qual" at a sentence's
# start) - without this, that heuristic would erase the very word evidence
# the F1 sink fix depends on.
ALL_SINK_MARKER_WORDS: frozenset[str] = frozenset(
    word for weights in SINK_MARKER_WORD_WEIGHTS.values() for word in weights
)

# --- Non-signal tokens: market/country names and the brand -----------------
# A real customer question routinely names a market ("Forever Kenya",
# "...au Kenya ?", "...i Norge?") or the brand ("Forever", "Aloe Vera").
# These are proper nouns spelled the same (or near-same) regardless of the
# writer's language, so they carry no language signal - and worse, a short
# market/country name can coincidentally collide with an unrelated
# language's closed-class word (this is exactly the defect
# ``config/alias_function_word_guard.py`` already documents and guards
# against for a different consumer, Estonian "Tai" colliding with Finnish
# "tai" = "or"). Excluding them from SCORING (coordinator review,
# 2026-09-19) stops a proper noun from diluting or tilting the margin
# between candidates; they are still counted toward MIN_TOKENS (message
# length), since that gate is about message length, not language evidence.
#
# Reused, not duplicated: every market/country name and its localized
# aliases already live in ``services.market_config`` (``markets.json``,
# ``global_directory_markets.json``, ``market_name_aliases.json`` via
# ``_localized_market_names()``, which already applies the function-word
# collision guard above). No new alias list is created here - this only
# flattens the existing names into single-word tokens for a membership
# check. The brand/product terms have no existing configured vocabulary
# (this repository has no product catalogue - see ``catalogue_scope`` in
# ``config/conversation_routes.json``, which says AskVera holds no product
# prices/catalogue at all), so the five-word brand list below is the
# smallest possible literal supplement, not an alias list.
_BRAND_TOKENS: frozenset[str] = frozenset({"forever", "living", "aloe", "vera", "fbo"})


@lru_cache(maxsize=1)
def _market_name_tokens() -> frozenset[str]:
    """Every configured market/country name, and every localized alias
    language ``services.market_config`` already loads, that is itself a
    SINGLE word ("Kenya", "Ghana", "Norge", "Sverige") - built once; the
    JSON it reads never changes within a process.

    Deliberately NOT split into word fragments. An earlier version split
    every name on whitespace, which turned a multi-word name into
    single-word fragments that can themselves be ordinary content or even
    function words in some language - "Costa Rica" produced the fragment
    "costa", which collided with the Italian verb "costa" ("it costs") and
    silently erased real Italian evidence from a sentence that merely
    mentioned an unrelated country. A multi-word name is therefore left
    alone here entirely (not masked) rather than risk that class of
    collision again; only a single, whole-word name is excluded, which
    cannot fragment into anything else.
    """
    from services.market_config import (
        _localized_market_names,
        load_global_directory_markets,
        load_market_config,
    )

    names: set[str] = set()
    for market in load_market_config()["markets"]:
        names.add(str(market.get("name", "")))
    for market in load_global_directory_markets():
        names.add(str(market.get("name", "")))
    for alias_list in _localized_market_names().values():
        names.update(alias_list)

    tokens: set[str] = set()
    for name in names:
        normalized = _normalize_marker(name)
        # A whole-name normalized form with no internal whitespace/punctuation
        # left is a single word; anything else (spaces, "&", "-", "/", "(")
        # is a multi-word or compound name and is skipped entirely.
        if normalized and re.fullmatch(r"[a-z]+", normalized) and len(normalized) >= 4:
            if normalized not in ALL_MARKER_WORDS:
                tokens.add(normalized)
    return frozenset(tokens)


def _is_non_signal_token(token: str) -> bool:
    """True for a token that is the brand or a configured market/country
    name (in any language) - excluded from marker-word scoring only."""
    return token in _BRAND_TOKENS or token in _market_name_tokens()


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
    # Cyrillic only: ђ ј љ њ ћ џ are genuinely Serbian-exclusive here (a
    # Cyrillic message using them cannot be any other route-copy language).
    # The Latin diacritics đ š ž č ć were REMOVED (Fable CX review finding
    # S4, 2026-09-19): they are NOT Serbian-specific at all - Croatian,
    # Bosnian and Montenegrin Latin script use exactly the same letters, so
    # crediting them made an ordinary Croatian sentence ("Koliko košta...")
    # look strongly Serbian and switch to it even on an English widget.
    # Latin-script Serbian is distinguished by its marker WORDS
    # (_RAW_MARKER_WORDS["sr"]) plus _SERBIAN_EXTRA_MARGIN /
    # MIN_WINNER_SHARE, never by these shared letters.
    "sr": frozenset("ђјљњћџЂЈЉЊЋЏ"),
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


def _distinctive_bonus(language: str, raw_message: str) -> tuple[float, float]:
    """Returns ``(total_bonus, exempt_bonus)``.

    ``exempt_bonus`` is word-equivalent evidence: ``_DISTINCTIVE_STRONG``
    letters (curated as genuinely exclusive to this language among ALL
    route and sink candidates - Spanish n-tilde/inverted punctuation,
    German sharp s, French cedilla/ligature/circumflex, Russian- and
    Serbian-exclusive Cyrillic letters) PLUS the POSITIONAL/pattern signals
    below (Italian's word-final accent, Finnish's doubled-vowel spelling,
    Serbian's "da li" idiom) - these are specific, multi-character shapes,
    not a bare shared letter, so they carry the same exclusivity a marker
    word would. Explicitly NOT exempt: ``_DISTINCTIVE_MODERATE``'s bare
    accented vowels (á/é/í/ó/ú etc.) - shared too broadly across Romance and
    other Latin-script languages (Fable CX re-review, 2026-09-19: a
    Portuguese or Hungarian sentence's own á/é/í/ó/ú handed Spanish a
    real-looking letter bonus with no Portuguese/Hungarian model to compare
    against, carrying two wrong-language switches past every other gate).
    ``resolve_answer_language``'s word-evidence floor uses ``exempt_bonus``
    as word-equivalent evidence; the moderate-only remainder contributes to
    score/margin, never to that floor.
    """
    exempt_bonus = 0.0
    strong = _DISTINCTIVE_STRONG.get(language)
    if strong:
        exempt_bonus += _STRONG_CHAR_WEIGHT * sum(1 for char in strong if char in raw_message)
    if language == "it":
        matches = len(_ITALIAN_WORD_FINAL_ACCENT.findall(raw_message))
        exempt_bonus += _ITALIAN_FINAL_ACCENT_WEIGHT * min(matches, 2)
    if language == "fi":
        matches = len(_FINNISH_DOUBLE_VOWEL.findall(raw_message))
        exempt_bonus += _FINNISH_DOUBLE_VOWEL_WEIGHT * min(matches, _FINNISH_DOUBLE_VOWEL_MAX_CREDITS)
    if language == "sr" and _SERBIAN_DA_LI.search(raw_message):
        exempt_bonus += _SERBIAN_DA_LI_WEIGHT

    bonus = exempt_bonus
    moderate = _DISTINCTIVE_MODERATE.get(language)
    if moderate:
        bonus += _MODERATE_CHAR_WEIGHT * sum(1 for char in moderate if char in raw_message)
    return bonus, exempt_bonus


def _sink_distinctive_bonus(language: str, raw_message: str) -> float:
    """Same mechanism as ``_distinctive_bonus``, scoped to the sink table -
    see ``_SINK_DISTINCTIVE_STRONG`` and ``_BULGARIAN_MEDIAL_YER`` above."""
    bonus = 0.0
    strong = _SINK_DISTINCTIVE_STRONG.get(language)
    if strong:
        bonus += _STRONG_CHAR_WEIGHT * sum(1 for char in strong if char in raw_message)
    if language == "bg":
        matches = len(_BULGARIAN_MEDIAL_YER.findall(raw_message))
        bonus += _BULGARIAN_MEDIAL_YER_WEIGHT * min(matches, _BULGARIAN_MEDIAL_YER_MAX_CREDITS)
    return bonus


def _any_sink_distinctive_letter_present(raw_message: str) -> bool:
    """True when the raw message contains ANY sink language's distinctive
    letter, anywhere - the unconditional half of the sink veto (coordinator:
    "Distinctive letters of a sink present -> no switch"), independent of
    score comparisons."""
    return any(character in raw_message for character in _ALL_SINK_DISTINCTIVE_LETTERS)


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


def _mask_non_signal_spans(message: str) -> str:
    """Blank out (replace with spaces, preserving length and every other
    character) every word span that is the brand or a configured
    market/country name. A real customer question routinely mixes a Latin
    brand name into an otherwise Cyrillic sentence ("Forever Кению") - unmasked,
    that would make the WHOLE message look script-mixed (ambiguous) even
    though the brand name carries no language signal either way. Masking
    before the script check, the marker-word scoring and the distinctive-
    character bonus (coordinator review, 2026-09-19) keeps all three
    consistent: a brand/market word is excluded from every kind of language
    evidence, not just word-counting.

    Beyond the configured brand/market list, a CAPITALIZED Latin-script word
    that is not itself a recognized marker word for any language (checked
    against ``ALL_MARKER_WORDS``, so a sentence-initial capitalized function
    word such as French "Quel" or German "Wie" is never touched) is masked
    too - it is very likely a proper noun or product/program name written in
    Latin script by convention regardless of the surrounding language
    ("Forever Bright Toothgel", "Forever Freedom"), the same situation the
    configured brand list exists for, just for a name not on that short
    list. This is a structural rule (capitalization + not-a-known-word), not
    a new word list, so it needs no per-word addition as new products or
    market names appear."""
    text = message or ""

    def _mask(match: re.Match[str]) -> str:
        raw = match.group(0)
        normalized = _normalize_marker(raw)
        if not normalized:
            return raw
        if _is_non_signal_token(normalized):
            return " " * len(raw)
        if (
            len(normalized) >= 3
            and raw[:1].isupper()
            and _LATIN_PATTERN.match(raw[:1])
            and normalized not in ALL_MARKER_WORDS
            and normalized not in ALL_SINK_MARKER_WORDS
        ):
            return " " * len(raw)
        return raw

    return _WORD_PATTERN.sub(_mask, text)


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
    ``winner_share`` is the fraction of the message's (non-brand/market)
    word tokens that are literally a marker word of ``language`` (unweighted
    membership, not the overlap-discounted score) - see
    ``resolve_answer_language``'s MIN_WINNER_SHARE gate, which uses this to
    require the winner's OWN evidence to dominate the message, not merely
    outscore weaker competitors (Fable CX review finding S4, 2026-09-19: a
    message in an unrecognised but closely related language - e.g.
    Portuguese, not a route-copy language - can rack up just enough
    Spanish-cognate score to clear the margin gate while most of the
    message's words match nothing in Spanish at all). ``winner_letter_evidence``
    is the distinctive-character/pattern bonus alone (see
    ``_distinctive_bonus``) that contributed to ``language``'s score - 0.0
    when its score is built entirely from marker words. ``sink_language`` and
    ``sink_score`` are the best-scoring "none of the above" SINK candidate
    (see ``_SINK_LANGUAGES``, Fable CX review finding F1, 2026-09-19) and its
    score - never a switch target itself, only evidence that the message
    probably isn't written in any of the 12 route-copy languages at all.
    ``winner_word_evidence`` is ``language``'s marker-word score PLUS only
    the EXEMPT (curated-exclusive) portion of its letter evidence - never
    the shared, moderate-accent portion - used by
    ``resolve_answer_language``'s word-evidence floor so a Latin-script
    switch can never be carried by broadly-shared accented vowels alone
    (Fable CX re-review, 2026-09-19; see ``_distinctive_bonus``).
    ``reason`` documents which branch produced the result.
    """

    language: str | None
    score: float
    runner_up: float
    reason: str
    winner_share: float = 0.0
    winner_letter_evidence: float = 0.0
    sink_language: str | None = None
    sink_score: float = 0.0
    winner_word_evidence: float = 0.0


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
    tokens = _tokenize(message)
    if not tokens:
        return Detection(None, 0.0, 0.0, "no_tokens")

    # Brand and market/country-name words carry no language signal and must
    # not dilute or tilt the margin between candidates, and must not make an
    # otherwise single-script sentence look script-mixed just because the
    # brand name is conventionally spelled in Latin script (coordinator
    # review, 2026-09-19) - masked out of every kind of evidence (script
    # signal, marker-word scoring, distinctive-character bonus) alike.
    # MIN_TOKENS in resolve_answer_language still counts the raw message.
    masked_message = _mask_non_signal_spans(message)

    script = _script_signal(masked_message)
    if script == "mixed":
        return Detection(None, 0.0, 0.0, "mixed_script")
    if script == "none":
        return Detection(None, 0.0, 0.0, "no_letters")

    if script == "cyrillic":
        eligible = tuple(language for language in candidates if language in {"ru", "sr"})
        sink_eligible = tuple(language for language in _SINK_LANGUAGES if language in _CYRILLIC_SINK_LANGUAGES)
    else:
        eligible = tuple(language for language in candidates if language not in _CYRILLIC_ONLY_LANGUAGES)
        sink_eligible = tuple(language for language in _SINK_LANGUAGES if language not in _CYRILLIC_SINK_LANGUAGES)

    scoring_tokens = _tokenize(masked_message)

    scores: dict[str, float] = {}
    hit_shares: dict[str, float] = {}
    letter_evidence: dict[str, float] = {}
    word_evidence: dict[str, float] = {}
    token_count = len(scoring_tokens)
    for language in eligible:
        weights = MARKER_WORD_WEIGHTS.get(language, {})
        word_score = sum(weights.get(token, 0.0) for token in scoring_tokens)
        bonus, exempt_bonus = _distinctive_bonus(language, masked_message)
        scores[language] = word_score + bonus
        letter_evidence[language] = bonus
        word_evidence[language] = word_score + exempt_bonus
        hit_count = sum(1 for token in scoring_tokens if token in weights)
        hit_shares[language] = (hit_count / token_count) if token_count else 0.0

    # SINK languages (F1): scored the same way, from the same masked tokens,
    # but never eligible to win the detection itself - only reported so
    # resolve_answer_language can veto a switch when one of them rivals the
    # route winner. See module docstring above _SINK_LANGUAGES.
    sink_scores: dict[str, float] = {
        language: (
            sum(SINK_MARKER_WORD_WEIGHTS.get(language, {}).get(token, 0.0) for token in scoring_tokens)
            + _sink_distinctive_bonus(language, masked_message)
        )
        for language in sink_eligible
    }
    sink_language: str | None = None
    sink_score = 0.0
    if sink_scores:
        best_sink_language, best_sink_score = max(sink_scores.items(), key=lambda item: item[1])
        if best_sink_score > 0:
            sink_language, sink_score = best_sink_language, best_sink_score

    if not scores:
        return Detection(None, 0.0, 0.0, "no_eligible_candidates", sink_language=sink_language, sink_score=sink_score)

    ordered = sorted(scores.items(), key=lambda item: (-item[1], candidates.index(item[0])))
    top_language, top_score = ordered[0]
    runner_up_score = ordered[1][1] if len(ordered) > 1 else 0.0

    if top_score <= 0:
        return Detection(
            None, 0.0, runner_up_score, "no_marker_hits", sink_language=sink_language, sink_score=sink_score
        )

    return Detection(
        top_language,
        top_score,
        runner_up_score,
        "scored",
        hit_shares[top_language],
        letter_evidence[top_language],
        sink_language,
        sink_score,
        word_evidence[top_language],
    )


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
# languages by coincidence more than most pairs here - and shares almost ALL
# of them with Croatian/Bosnian specifically, since Latin-script Serbian,
# Croatian and Bosnian are the same pluricentric language for this purpose;
# require extra margin whenever Serbian is the candidate winning against any
# other candidate. Kept at 1.5 even after removing the (incorrectly
# Serbian-attributed) diacritic bonus - see _DISTINCTIVE_STRONG's "sr" entry
# - specifically because a lower value let a genuine Croatian sentence
# ("Kako mogu vratiti proizvod...") cross into "sr" (Fable S4, 2026-09-19).
_SERBIAN_EXTRA_MARGIN = 1.5

# Cyrillic-script messages: ru and sr are the only eligible candidates (see
# detect_message_language), so the false-positive risk that justifies the
# higher Latin-script floor (many languages' function words overlapping)
# does not apply the same way - the real risk is ru/sr confusion, which the
# distinctive-letter evidence (_DISTINCTIVE_STRONG) is built to resolve.
CYRILLIC_SERBIAN_EXTRA_MARGIN = 1.5

# A Cyrillic Russian message with a Russian-EXCLUSIVE letter (ы/э/ъ/ё) or,
# for Serbian, Serbian-exclusive letters (see _DISTINCTIVE_STRONG) switches
# even on a thin score - this is what lets short, mostly-content-word
# customer questions (few closed-class words relative to their length)
# still switch (coordinator review, 2026-09-18). Below this, the ultra-low
# floor is not trustworthy any more (Fable S4, 2026-09-19 - see the
# words-only tier below).
# was tuned for genuine, short, word-sparse Russian questions, but it is
# equally happy to wave through a Ukrainian (or Bulgarian/Kazakh/Kyrgyz)
# message that merely shares a common Cyrillic pronoun/preposition with
# Russian and nothing else - neither score nor margin can tell those two
# situations apart (a probed Ukrainian sentence scored HIGHER on both than
# the weakest genuine Russian one). What DOES separate them is
# ``winner_letter_evidence``: every genuine-but-thin Russian probe that
# survives this gate contains at least one Russian-EXCLUSIVE Cyrillic letter
# (ы/э/ъ/ё - not used in Ukrainian, Bulgarian, Kazakh, Kyrgyz or Serbian
# Cyrillic at all), while the false-positive Ukrainian probe contains none.
# So: with letter evidence, the existing ultra-low floor still applies
# (unchanged behaviour for the case it was built for); WITHOUT it, Russian
# must clear the same winner-share bar every other language does.
CYRILLIC_MIN_SCORE_WITH_LETTER_EVIDENCE = 0.5
CYRILLIC_MIN_MARGIN_WITH_LETTER_EVIDENCE = 0.5
CYRILLIC_MIN_SCORE_WORDS_ONLY = 1.5
CYRILLIC_MIN_MARGIN_WORDS_ONLY = 1.5

# Fable CX review finding S4 (2026-09-19): beating the runner-up is not
# enough on its own - the winner's OWN evidence must be a real fraction of
# the message, not a couple of cognates that happen to have no competition.
# This is what stops a Portuguese message (Portuguese is not a route-copy
# language, so it is never itself a candidate) from being waved through to
# Spanish just because Portuguese and Spanish share enough vocabulary to
# clear MIN_SCORE/MIN_MARGIN while most of the message's words match
# nothing in Spanish at all. Tuned against both acceptance sets in
# tests/unit/test_cx_answer_language.py (kept at 100% precision, unchanged
# recall) and against the non-route-copy negative set (pt/hr/uk/tr messages
# on an "en" widget - see TestNonRouteCopySelectedLanguage).
MIN_WINNER_SHARE = 0.1
# The stricter share bar for a Cyrillic winner with no letter evidence at
# all (see CYRILLIC_MIN_SCORE_WORDS_ONLY above) - set just above the
# false-positive Ukrainian probe's own share (0.2) and just below the
# genuine word-heavy Russian brand/market probes' shares (>= 0.375 once
# letter-less; the letter-bearing ones use the lenient bar instead).
CYRILLIC_MIN_WINNER_SHARE_WORDS_ONLY = 0.3

# Fable CX review finding F1 (2026-09-19): the margin a "none of the above"
# SINK language must be beaten by, for resolve_answer_language's sink veto.
# Deliberately the plain base margin (MIN_MARGIN), not whatever
# near-pair/Serbian-inflated `required_margin` the route winner itself had
# to clear - the sink veto is a separate safety net, not a repeat of the
# same near-pair logic (reusing the inflated margin would veto nearly every
# genuine Latin-Serbian sentence against its own hr/bs sink, whose marker
# words mirror Serbian's almost exactly by construction).
SINK_VETO_MARGIN = MIN_MARGIN

# Fable CX re-review (2026-09-19): a Latin-script switch must never be
# carried by shared, MODERATE accented-vowel evidence alone - see
# _distinctive_bonus's docstring for the concrete failure (Portuguese/
# Hungarian sentences with just one matching Spanish marker word, but
# enough á/é/í/ó/ú to clear MIN_SCORE/MIN_MARGIN and MIN_WINNER_SHARE
# regardless). MIN_WORD_EVIDENCE requires the winner's marker-word score
# PLUS only its EXEMPT (curated-exclusive) letter evidence - ñ/¿/¡ for
# Spanish, ß for German, etc. - to clear a floor on its own;
# MIN_LATIN_SWITCH_SHARE is a stricter companion share bar for this same
# gate (separate from the general MIN_WINNER_SHARE above, which the
# S4 gate already checked earlier and stays unchanged for every other
# purpose). Cyrillic-script switches are unaffected - they have their own,
# already-split lenient/strict tiers keyed on winner_letter_evidence.
MIN_WORD_EVIDENCE = 2.0
MIN_LATIN_SWITCH_SHARE = 0.3


def _normalize_language_code(code: str) -> str:
    """Fold a BCP-47-ish language tag down to its base subtag, casefolded
    ("pt-BR" -> "pt", "sr-Latn" -> "sr", "sr-ME" -> "sr", "SR_RS" -> "sr").
    Used only to compare the SELECTED widget language against
    ``ROUTE_COPY_LANGUAGES`` - the returned ``AnswerLanguage.answer_language``
    on a non-switch is always the original, un-normalized ``selected_language``
    the caller passed, never this folded form."""
    return (code or "").strip().split("-")[0].split("_")[0].casefold()


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


_EPSILON = 1e-9


def _required_thresholds(detection: Detection, script: str, normalized_selected: str) -> tuple[float, float, float]:
    """The (required_score, required_margin, required_share) a winning
    ``detection`` must clear, given the message's script and the selected
    widget language - split out of ``resolve_answer_language`` purely to
    keep that function's own branching manageable."""
    required_share = MIN_WINNER_SHARE

    if script == "cyrillic":
        if detection.language == "ru" and detection.winner_letter_evidence <= 0:
            # No Russian-exclusive letter (ы/э/ъ/ё) anywhere in the message:
            # the score is built entirely from marker words Russian shares
            # with its closest Cyrillic-script relatives (Ukrainian,
            # Bulgarian, Kazakh, Kyrgyz), so the low floor below - tuned for
            # genuine word-sparse Russian questions - is not trustworthy
            # here (Fable S4). Fall back to the stricter, words-only bar.
            required_score = CYRILLIC_MIN_SCORE_WORDS_ONLY
            required_margin = CYRILLIC_MIN_MARGIN_WORDS_ONLY
            required_share = CYRILLIC_MIN_WINNER_SHARE_WORDS_ONLY
        else:
            required_score = CYRILLIC_MIN_SCORE_WITH_LETTER_EVIDENCE
            required_margin = CYRILLIC_MIN_MARGIN_WITH_LETTER_EVIDENCE
        if detection.language == "sr":
            required_margin += CYRILLIC_SERBIAN_EXTRA_MARGIN
        return required_score, required_margin, required_share

    required_score = MIN_SCORE
    required_margin = MIN_MARGIN
    if frozenset({detection.language, normalized_selected}) <= _NEAR_LANGUAGE_GROUP:
        required_margin += _NEAR_PAIR_EXTRA_MARGIN
    if detection.language == "sr":
        required_margin += _SERBIAN_EXTRA_MARGIN
    return required_score, required_margin, required_share


def _sink_veto_reason(detection: Detection, message: str) -> str | None:
    """"None of the above" SINK veto (Fable CX review finding F1,
    2026-09-19): a message actually written in a non-route language
    (Portuguese, Hungarian, Croatian, ...) can score a real route-copy
    relative highly enough to pass every other gate, because the
    relative's vocabulary genuinely overlaps. Two independent signals
    block the switch instead of guessing which of the 12 the message
    "really" is:
      1. any sink language's distinctive letter is present anywhere in the
         message (unconditional - see _any_sink_distinctive_letter_present);
      2. the best-scoring sink rivals the route winner - it either
         outscores it outright, or sits within SINK_VETO_MARGIN of it.
    Returns the veto reason string, or None when the switch may proceed.
    """
    if _any_sink_distinctive_letter_present(message):
        return "non_route_language_likely"
    if detection.sink_language is None:
        return None
    # A dedicated margin, not the (possibly inflated) `required_margin` the
    # route winner itself had to clear: hr/bs are sinks against "sr"
    # specifically BECAUSE their marker words mirror it almost exactly (see
    # _SINK_RAW_MARKER_WORDS' "hr"/"bs" note), so reusing _SERBIAN_EXTRA_MARGIN
    # here too would veto nearly every genuine Latin-Serbian sentence
    # outright. SINK_VETO_MARGIN is the plain base margin every route pair
    # must already clear against ANOTHER route candidate - the sink is held
    # to that same bar, no more, no less.
    sink_margin = detection.score - detection.sink_score
    if detection.sink_score >= detection.score or sink_margin < SINK_VETO_MARGIN - _EPSILON:
        return "non_route_language_likely"
    return None


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

    # Fable CX review finding S4 (2026-09-19): the detector can only ever
    # recognise the 12 ROUTE_COPY_LANGUAGES. If the SELECTED widget language
    # is some other configured language (e.g. Portuguese, Croatian,
    # Ukrainian, Turkish - today unreachable via ChatRequest, but latent the
    # moment config/markets.json's other configured languages are enabled),
    # the detector cannot tell that the message is ALREADY written in the
    # selected language - "matches_selected" below can never fire for it -
    # so it would confidently "detect" the closest route-copy relative
    # instead (Portuguese -> Spanish, Croatian/Ukrainian -> Serbian/Russian,
    # Turkish -> French/German, ...) and switch to a language the user never
    # asked for. There is no safe detection to attempt here: bail out before
    # ever calling detect_message_language.
    normalized_selected = _normalize_language_code(selected_language)
    if normalized_selected not in ROUTE_COPY_LANGUAGES:
        return AnswerLanguage(selected_language, False, "selected_language_not_route_copy")

    detection = detect_message_language(message, candidates=ROUTE_COPY_LANGUAGES)
    if detection.language is None:
        return AnswerLanguage(selected_language, False, detection.reason)

    if detection.language == normalized_selected:
        return AnswerLanguage(selected_language, False, "matches_selected")

    if detection.language not in ROUTE_COPY_LANGUAGES:
        return AnswerLanguage(selected_language, False, "no_route_copy")  # pragma: no cover - defensive

    script = _script_signal(message)
    margin = detection.score - detection.runner_up
    required_score, required_margin, required_share = _required_thresholds(detection, script, normalized_selected)

    # The winner must not just outscore the runner-up; its OWN evidence must
    # be a real fraction of the message (Fable S4) - otherwise a handful of
    # cognates with no real competition (Portuguese scored as Spanish) can
    # clear the margin gate below on evidence that barely touches the
    # message at all.
    if detection.winner_share < required_share:
        return AnswerLanguage(selected_language, False, "below_winner_share")

    # Fable CX re-review (2026-09-19): letters alone - specifically the
    # broadly-shared MODERATE accented-vowel bonus - must never carry a
    # Latin-script switch on their own, even once the two gates above are
    # cleared (a Portuguese/Hungarian sentence can still pass both with just
    # one matching Spanish marker word). This gate only engages when
    # non-exempt letter evidence actually contributed to the score
    # (``detection.score`` exceeds ``winner_word_evidence`` - i.e. some
    # MODERATE/shared bonus is present); a switch built entirely from
    # marker words (no letter contribution at all, exempt or otherwise) has
    # nothing for this gate to distrust and is left to the ordinary
    # MIN_WINNER_SHARE gate above, so a real but modest-share English
    # sentence with zero letter evidence isn't penalized for a risk that
    # doesn't apply to it. Cyrillic already has its own, separately-tuned
    # lenient/strict split (see _required_thresholds), so this gate applies
    # only to the Latin-script branch.
    non_exempt_letter_evidence = detection.score - detection.winner_word_evidence
    if (
        script != "cyrillic"
        and non_exempt_letter_evidence > _EPSILON
        and (
            detection.winner_word_evidence < MIN_WORD_EVIDENCE - _EPSILON
            or detection.winner_share < MIN_LATIN_SWITCH_SHARE - _EPSILON
        )
    ):
        return AnswerLanguage(selected_language, False, "insufficient_word_evidence")

    # Scores are sums of float weights (0.2/0.3/0.5/1.0/1.5/2.0/3.0 etc.), so
    # a margin that is mathematically exactly the threshold can land a hair
    # under it due to binary floating-point rounding (e.g. 3.1 - 2.1 ==
    # 0.9999999999999996 in IEEE 754 double precision). A tiny epsilon
    # absorbs that rounding without weakening the documented threshold.
    if detection.score < required_score - _EPSILON or margin < required_margin - _EPSILON:
        return AnswerLanguage(selected_language, False, "below_threshold")

    sink_veto = _sink_veto_reason(detection, message)
    if sink_veto is not None:
        return AnswerLanguage(selected_language, False, sink_veto)

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
