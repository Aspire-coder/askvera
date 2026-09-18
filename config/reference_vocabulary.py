"""Closed-class reference vocabulary for unresolved back-references (task A7).

Contrastive determiners ("the other one") and ordinals ("the first one",
"the last one") are bounded, closed grammatical word classes in every
language a language can have only so many of them, and a language does not
gain a new one the way a product line gains a new topical phrase. That is
what makes this module safe to key by language code and audit as a whole: a
phrase list for "ways of asking about the other market" would keep growing
forever and would still miss most of them, which is exactly why Lane A's
original English anaphor-phrase-list patch for this task was rejected by the
coordinator (see docs/conversation-quality/TASK_BOARD.md, "Rejected worker
proposals", and docs/conversation-quality/codex-requests/A7-unresolved-reference.md).
This module lists the closed class instead of the open one.

Tokens below are written already casefolded and with accents/diacritics
stripped, matching the normalization
app.orchestrator.chat_orchestrator._follow_up_tokens applies to a message
before comparing it against LOCALIZED_FOLLOW_UP_* vocabulary elsewhere in
this codebase (NFKD-decompose, drop combining marks, casefold, then split on
word characters). app.orchestrator.reference_resolution tokenizes the
incoming message the same way and checks membership, so an inflected or
accented surface form ("l'autre" -> tokens "l", "autre"; "den anderen" ->
"den", "anderen"; "la otra" -> "la", "otra"; "première" -> "premiere") is
matched without a second, accented spelling being written out here.

Language coverage is exactly the set of widget languages
services/market_config.py's config/markets.json configures: en, fr, de, nl,
it, pt, es, fi, no, sv. A language code that is not a key of
LOCALIZED_CONTRASTIVE_TOKENS is UNKNOWN to this module and must fail
conservative (A7 design rule 5): app.orchestrator.reference_resolution never
clarifies or rewrites for a language it does not recognize here, so an
unsupported language leaves today's behaviour exactly as it was.
"""

from __future__ import annotations

# Contrastive determiners/pronouns ("other", "another", "others" and each
# language's own word forms). Deliberately excludes ordinal words, and
# deliberately excludes a handful of words that are genuinely ambiguous
# between "other" and "second" in their own language (Swedish "andra",
# Norwegian "andre", Finnish "toinen" all serve both meanings). Listing an
# ambiguous word only here, never in LOCALIZED_ORDINAL_TOKENS, is a
# deliberate safety choice: on either reading, asking a brief clarifying
# question (the contrastive path) is the safe response, whereas resolving it
# as an ordinal (the ordinal path) risks confidently answering the wrong
# market when the word actually meant "other". See LOCALIZED_ORDINAL_TOKENS.
LOCALIZED_CONTRASTIVE_TOKENS: dict[str, frozenset[str]] = {
    "en": frozenset({"other", "others", "another"}),
    "fr": frozenset({"autre", "autres"}),
    "de": frozenset({"andere", "anderen", "anderes", "anderer", "andres"}),
    "nl": frozenset({"andere", "ander"}),
    "it": frozenset({"altro", "altra", "altri", "altre"}),
    "pt": frozenset({"outro", "outra", "outros", "outras"}),
    "es": frozenset({"otro", "otra", "otros", "otras"}),
    "fi": frozenset({"toinen", "toista", "toisen", "muu", "muut"}),
    "no": frozenset({"andre", "annen", "annet"}),
    "sv": frozenset({"andra", "annan", "annat"}),
}

# Ordinal words that resolve deterministically to one candidate by order of
# first mention in the user's own turns (A7 design rule 3). Each token maps
# to a named slot rather than a fixed number, because "first"/"last" are
# relative to however many candidates the conversation actually offered:
# app.orchestrator.reference_resolution turns a slot into an index only after
# it knows the candidate count. "former"/"latter" only ever resolve when
# there are exactly two candidates - with more than two they are genuinely
# ambiguous, so reference_resolution leaves them unresolved rather than
# guessing which two of several the speaker meant.
#
# A word that is ambiguous between "other" and "second" in its own language
# is intentionally left out of this table (see LOCALIZED_CONTRASTIVE_TOKENS's
# docstring) - Swedish and Norwegian therefore have no token for slot
# "second", and Finnish has no token for "second" either. Each is still fully
# covered for "first"/"last", which is what the acceptance tests exercise.
LOCALIZED_ORDINAL_TOKENS: dict[str, dict[str, str]] = {
    "en": {
        "first": "first",
        "second": "second",
        "third": "third",
        "last": "last",
        "former": "former",
        "latter": "latter",
    },
    "fr": {
        "premier": "first",
        "premiere": "first",
        "deuxieme": "second",
        "seconde": "second",
        "troisieme": "third",
        "dernier": "last",
        "derniere": "last",
    },
    "de": {
        "erste": "first",
        "ersten": "first",
        "erster": "first",
        "erstes": "first",
        "zweite": "second",
        "zweiten": "second",
        "zweiter": "second",
        "zweites": "second",
        "dritte": "third",
        "letzte": "last",
        "letzten": "last",
        "letzter": "last",
        "letztes": "last",
    },
    "nl": {
        "eerste": "first",
        "tweede": "second",
        "derde": "third",
        "laatste": "last",
    },
    "it": {
        "primo": "first",
        "prima": "first",
        "secondo": "second",
        "seconda": "second",
        "terzo": "third",
        "terza": "third",
        "ultimo": "last",
        "ultima": "last",
    },
    "pt": {
        "primeiro": "first",
        "primeira": "first",
        "segundo": "second",
        "segunda": "second",
        "terceiro": "third",
        "terceira": "third",
        "ultimo": "last",
        "ultima": "last",
    },
    "es": {
        "primero": "first",
        "primera": "first",
        "segundo": "second",
        "segunda": "second",
        "tercero": "third",
        "tercera": "third",
        "ultimo": "last",
        "ultima": "last",
    },
    "fi": {
        "ensimmainen": "first",
        "ensimmaista": "first",
        "viimeinen": "last",
        "viimeista": "last",
    },
    "no": {
        "forste": "first",
        "siste": "last",
    },
    "sv": {
        "forsta": "first",
        "sista": "last",
    },
}

# A contrastive/ordinal token counts as a MARKET reference only when the
# message is otherwise empty of content (coordinator review, 2026-09-18: a
# reference token counts whatever noun phrase it modifies, so "the first
# ORDER", "the last DAY", "the other FEE" are not market references at all -
# resolving them would confidently answer the wrong question, not just the
# wrong market). The two tables below implement that check:
#
# LOCALIZED_NON_CONTENT_TOKENS - articles, prepositions, conjunctions, WH-
# question words and copula/auxiliary verbs, i.e. the closed grammatical
# classes a short question is built from around its one content word. These
# are stripped, along with the matched reference token itself, before asking
# "is anything left?". This mirrors chat_orchestrator.py's own
# LOCALIZED_FOLLOW_UP_FUNCTION_WORDS / LOCALIZED_FOLLOW_UP_STOP_WORDS and the
# opener phrases in LOCALIZED_TOPIC_SHIFT_OPENERS (not imported - see
# app/orchestrator/reference_resolution.py's docstring on why - but the same
# closed-class technique, extended with the WH/aux words a bare "what
# about"/"qu'en est-il"/"was ist mit" opener needs).
#
# This list is deliberately allowed to be incomplete per language: a word
# missing from it only ever makes the leftover-content check see MORE
# content than there really is, which only ever suppresses a reference this
# module could have resolved (the safe, unchanged direction). It can never
# cause a false positive - a false positive needs an EMPTY leftover, and a
# missing function word only ever adds to that leftover, never removes from
# it. So under-covering a language here is a documented limitation (missed
# clarifications/resolutions in unanticipated phrasings), never a new risk.
LOCALIZED_NON_CONTENT_TOKENS: dict[str, frozenset[str]] = {
    "en": frozenset({
        "the", "a", "an", "of", "to", "is", "are", "was", "were", "do", "does", "did",
        "what", "how", "about", "there", "any",
    }),
    "fr": frozenset({
        "le", "la", "les", "l", "du", "des", "d", "a", "au", "aux", "pour", "et", "en",
        "qu", "est", "il", "y", "de",
    }),
    "de": frozenset({
        "der", "die", "das", "den", "dem", "ein", "eine", "im", "fur", "fuer", "nach",
        "mit", "und", "aus", "von", "was", "ist",
    }),
    "nl": frozenset({
        "de", "het", "een", "van", "voor", "naar", "in", "met", "en", "hoe", "zit",
    }),
    "it": frozenset({
        "il", "lo", "i", "gli", "di", "della", "alla", "ad", "nel", "nella", "per",
        "e", "quanto", "riguarda", "l",
    }),
    "pt": frozenset({
        "o", "os", "as", "do", "da", "dos", "no", "na", "nos", "nas", "em", "ao", "aos",
        "e", "quanto",
    }),
    "es": frozenset({
        "el", "los", "las", "del", "al", "para", "y", "que", "hay",
    }),
    "fi": frozenset({
        "enta", "se", "mika", "onko", "mita",
    }),
    "sv": frozenset({
        "for", "till", "om", "och", "hur", "ar", "det", "med", "den",
    }),
    "no": frozenset({
        "for", "til", "og", "hva", "med", "den", "er",
    }),
}

# The only real-world-content-free nouns a bare reference word may still
# stand next to: a generic pronoun head ("the first ONE") or a generic
# place/market head. Anything else left over is real content, so the
# message is not a market reference.
LOCALIZED_PROP_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset({"one", "ones", "country", "market", "place"}),
    "fr": frozenset({"pays", "marche", "endroit"}),
    "de": frozenset({"land", "markt", "ort"}),
    "nl": frozenset({"land", "markt", "plaats"}),
    "it": frozenset({"paese", "mercato", "posto"}),
    "pt": frozenset({"pais", "mercado", "lugar"}),
    "es": frozenset({"pais", "mercado", "lugar"}),
    "fi": frozenset({"maa", "markkina", "paikka"}),
    "sv": frozenset({"land", "marknad", "plats"}),
    "no": frozenset({"land", "marked", "sted"}),
}

# Every language this module covers must key all four tables identically, so
# a lookup by language code can test one table and trust the others.
assert set(LOCALIZED_CONTRASTIVE_TOKENS) == set(LOCALIZED_ORDINAL_TOKENS)
assert set(LOCALIZED_CONTRASTIVE_TOKENS) == set(LOCALIZED_NON_CONTENT_TOKENS)
assert set(LOCALIZED_CONTRASTIVE_TOKENS) == set(LOCALIZED_PROP_WORDS)
SUPPORTED_REFERENCE_LANGUAGES = frozenset(LOCALIZED_CONTRASTIVE_TOKENS)
