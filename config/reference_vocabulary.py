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

# Every language this module covers must key both tables identically, so a
# lookup by language code can test one table and trust the other.
assert set(LOCALIZED_CONTRASTIVE_TOKENS) == set(LOCALIZED_ORDINAL_TOKENS)
SUPPORTED_REFERENCE_LANGUAGES = frozenset(LOCALIZED_CONTRASTIVE_TOKENS)
