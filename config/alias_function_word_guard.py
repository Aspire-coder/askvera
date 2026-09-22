r"""Exclude closed-class function words from ``market_name_aliases.json``.

``config/market_name_aliases.json`` is machine-generated (its own ``source``
field says "Node Intl.DisplayNames / Unicode CLDR") and lists, for each
market, every locale's own name for that country. CLDR does not know that a
short country name can *also* be an ordinary closed-class word (article,
conjunction, preposition, pronoun, auxiliary) in a completely unrelated
language: Estonian's name for Thailand is "Tai", which is also the everyday
Finnish word for "or" ("Voinko maksaa kortilla tai kateisella?" - "Can I pay
by card or cash?"). Loaded unfiltered, that turns an ordinary Finnish
question into a spurious Thailand directory lookup.

This module is the general guard for that whole class of defect, applied at
the alias LOADING layer (``services/market_config.py``'s
``_localized_market_names()``), not as a one-off deletion of "Tai" from the
generated JSON. An alias is excluded only when it, as a whole word, equals a
word this repository's own reviewed vocabulary already lists as a member of
a CLOSED grammatical class - never because it happens to *also* be a country
name in some language (that is real, accepted ambiguity; see "Known
limitation" below).

## Where the function words come from

1. ``config/reference_vocabulary.py``'s ``LOCALIZED_NON_CONTENT_TOKENS`` -
   articles, prepositions, conjunctions, WH-question words and copula/
   auxiliary verbs, already reviewed and used for the same closed-class
   purpose (A7 unresolved-reference leftover-content check).
2. ``app/orchestrator/chat_orchestrator.py``'s
   ``LOCALIZED_FOLLOW_UP_FUNCTION_WORDS`` and
   ``LOCALIZED_FOLLOW_UP_STOP_WORDS`` - articles/prepositions/conjunctions,
   and WH-question words/pronouns/copula, respectively, already reviewed for
   the multilingual short-follow-up mechanism (W14/W14b).

Both are imported lazily, inside ``_closed_class_function_words()`` rather
than at module import time, because ``chat_orchestrator.py`` itself imports
from ``services/market_config.py`` (which is this guard's only caller) - a
top-of-module import here would be circular. By the time anything actually
*calls* this guard (at request-handling time, or in a test that calls
``services.market_config.find_market_mentions``), both modules have already
finished loading, so the delayed import resolves normally.

## The supplement - closed-class words ONLY

``_SUPPLEMENTARY_CLOSED_CLASS_FUNCTION_WORDS`` below adds words that are
proven necessary (they collide with a real alias - see
``docs/conversation-quality/phase2/ALIAS_COLLISION_AUDIT.md`` for the full
scan) but are not yet in either reviewed vocabulary above. Every entry here
MUST be a closed-class word (conjunction, preposition, article, pronoun or
auxiliary) in the language it is keyed under, and nothing else - this
supplement is not a place to exclude a content word (a real noun) just
because it happens to collide with a country name. Finnish "tai" ("or") is
the only entry driving this change; it is a coordinating conjunction, the
most closed of closed classes.

## Known limitation - genuine content-word ambiguity is NOT excluded

Some market aliases are real country names in one language and an ordinary
content noun in another - Chile/Chili ("chili pepper"), Turkey ("the bird"),
Mali (no known collision, but the shape is the same). Those are genuine
ambiguity, not a defect this guard fixes: a content noun is not a member of
any closed grammatical class, so it is never a candidate for exclusion here.
This is documented, not silently swallowed - see the audit doc referenced
above.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

from utils.logging import get_logger

LOGGER = get_logger("config.alias_function_word_guard")

# Closed-class words proven necessary by the audit (see module docstring)
# but not yet present in either reviewed vocabulary this guard reads from.
# Keep this small and keyed by language code; every value MUST be a
# conjunction, preposition, article, pronoun or auxiliary in that language -
# never a content word, however tempting it is to silence a false positive.
_SUPPLEMENTARY_CLOSED_CLASS_FUNCTION_WORDS: dict[str, frozenset[str]] = {
    # "tai" = Finnish coordinating conjunction "or" (collides with the
    # Estonian CLDR name for Thailand - the defect this change fixes).
    "fi": frozenset({"tai"}),
}


def _unaccented(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _normalize_function_word(text: str) -> str:
    """Fold a word the same way ``chat_orchestrator._follow_up_tokens`` does,
    so a function word sourced from either reviewed vocabulary or the
    supplement above compares equal regardless of accents/case."""
    return _unaccented(text or "").casefold().strip()


@lru_cache(maxsize=1)
def _closed_class_function_words() -> frozenset[str]:
    """Return every closed-class function word this guard knows about,
    normalized (accent-stripped, casefolded) for comparison against a
    normalized alias. See the module docstring for provenance and why the
    imports below are deliberately deferred rather than top-level."""
    from app.orchestrator.chat_orchestrator import (
        LOCALIZED_FOLLOW_UP_FUNCTION_WORDS,
        LOCALIZED_FOLLOW_UP_STOP_WORDS,
    )
    from config.reference_vocabulary import LOCALIZED_NON_CONTENT_TOKENS

    words: set[str] = set()
    for token_set in LOCALIZED_NON_CONTENT_TOKENS.values():
        words.update(_normalize_function_word(token) for token in token_set)
    words.update(_normalize_function_word(token) for token in LOCALIZED_FOLLOW_UP_FUNCTION_WORDS)
    words.update(_normalize_function_word(token) for token in LOCALIZED_FOLLOW_UP_STOP_WORDS)
    for token_set in _SUPPLEMENTARY_CLOSED_CLASS_FUNCTION_WORDS.values():
        words.update(_normalize_function_word(token) for token in token_set)
    return frozenset(words)


def is_function_word_alias(alias: str) -> bool:
    """True when ``alias``, taken as a whole word, equals a known
    closed-class function word.

    Only a single-token alias can ever collide: every closed-class word this
    guard knows about is one token, so a multi-word alias ("Amerika
    Birlesik Devletleri") can never match here regardless of its content.
    """
    normalized = _normalize_function_word(alias)
    if not normalized or " " in normalized:
        return False
    return normalized in _closed_class_function_words()


def filter_function_word_aliases(
    names: dict[str, list[str]],
) -> tuple[dict[str, list[str]], tuple[tuple[str, str], ...]]:
    """Return ``(filtered_names, excluded)`` for a raw ``market_name_aliases.json``
    ``"names"`` mapping (market code -> list of alias strings).

    ``excluded`` is every ``(market_code, alias)`` pair this guard removed, in
    the mapping's own iteration order, so a caller can log or audit exactly
    what was dropped and why (see the module docstring - this is what makes
    the exclusion auditable rather than a silent deletion).
    """
    filtered: dict[str, list[str]] = {}
    excluded: list[tuple[str, str]] = []
    for code, aliases in names.items():
        kept: list[str] = []
        for alias in aliases:
            if is_function_word_alias(alias):
                excluded.append((code, alias))
            else:
                kept.append(alias)
        filtered[code] = kept
    return filtered, tuple(excluded)
