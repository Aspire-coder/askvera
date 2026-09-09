"""Catalogue-based country-name expansion for retrieval queries.

A reader asking about "Reunion" does not match a document that writes
"Réunion". The index stores `content` as plain text with no analysis settings,
so the standard analyser does not fold diacritics and the two spellings are
different terms. Market *resolution* already copes - both spellings are
separate entries in the name catalogue and both resolve to `RE` - but nothing
was putting the document's spelling into the search text.

This module adds that spelling as an extra query. It does three things
deliberately narrowly:

- **The original question is preserved.** Expansion appends; it never rewrites
  or replaces. The caller keeps the original first, where the provider gives it
  full weight and every later query 0.88.
- **Only markets the reader actually named.** Resolution goes through
  `find_market_mentions`, which refuses an ambiguous or qualified mention
  rather than guessing, so an unrelated country cannot arrive here.
- **Two variants per market at most, chosen by rule.** The catalogue holds
  every CLDR localisation - 19 names for Réunion, 35 for Equatorial Guinea,
  most in scripts no approved document uses. Adding them all would be noise
  bought at the cost of precision.

The two rules are:

1. A variant that differs from what the reader wrote **only by diacritics**.
   This is the defect above, and nothing else.
2. The market's **configured canonical name**, which is the name the rest of
   the system already uses for that market. This is what carries `DRC` to
   `Democratic Republic of Congo`.

What this is not: translation. "Guinée" is not added for an English "Guinea"
question - it folds to `guinee`, not `guinea`, so rule 1 does not reach it, and
which language a document may be drawn from is a scope question that belongs to
the language filter, not to query text.

**This cannot widen access.** Locale searches filter on the session's country,
which the caller passes separately; global directory targeting derives from the
original message in `_directory_target_country_names`. Neither reads these
queries. That is asserted in `tests/unit/test_country_name_expansion.py` against
the eligible document set rather than left as a claim about unchanged filter
code, because a changed query can still change planning and scope selection.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from config import settings
from services.market_config import (
    _localized_market_names,
    find_market_mentions,
    load_global_directory_markets,
    load_market_config,
)

# Bounds. Every added query is another pair of searches per request, and a
# question naming several markets is the case that multiplies fastest.
_MAX_MARKETS = 3
_MAX_VARIANTS_PER_MARKET = 2
_MAX_QUERIES = 4


def _fold(value: str) -> str:
    """Case- and diacritic-insensitive form, for comparing spellings only.

    Deliberately not `_normalize_market_text`: that folds case but keeps
    diacritics, which is right for matching a name against a catalogue that
    lists both spellings separately, and useless for recognising that the two
    spellings are the same name.
    """
    decomposed = unicodedata.normalize("NFKD", value or "").casefold()
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", stripped, flags=re.UNICODE).strip()


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Per market code: its configured name, and every approved name for it.

    Cached like the rest of the market configuration. The catalogue is 166
    markets and a few thousand names; rebuilding it per request is the mistake
    that put 913ms on the request path once already.
    """
    canonical: dict[str, str] = {}
    for market in load_market_config().get("markets", []):
        if not market.get("enabled", True):
            continue
        code = str(market.get("code") or "").upper()
        name = str(market.get("name") or "").strip()
        if code and name:
            canonical.setdefault(code, name)

    names: dict[str, list[str]] = {}
    for market in [*load_market_config().get("markets", []), *load_global_directory_markets()]:
        code = str(market.get("code") or "").upper()
        name = str(market.get("name") or "").strip()
        if code and name:
            names.setdefault(code, []).append(name)
            canonical.setdefault(code, name)
    for code, localized in _localized_market_names().items():
        for name in localized:
            cleaned = str(name).strip()
            if cleaned:
                names.setdefault(str(code).upper(), []).append(cleaned)

    return {
        code: (canonical.get(code, ""), tuple(dict.fromkeys(entries)))
        for code, entries in names.items()
    }


def _written_span(message: str, code: str) -> tuple[str, int, int] | None:
    """The longest approved name for this market as the reader actually typed it.

    Longest first so a question naming "Equatorial Guinea" reports that, not the
    "Guinea" inside it. Returns None when no approved name appears literally -
    which happens when punctuation differs, as in "Cote d Ivoire" against the
    configured "Cote d'Ivoire". Substituting into a span we could not locate
    would mean guessing where the name was, so nothing is added instead.
    """
    _, names = _catalogue().get(code, ("", ()))
    for name in sorted(names, key=len, reverse=True):
        match = re.search(
            rf"(?<!\w){re.escape(name)}(?!\w)", message or "", flags=re.IGNORECASE
        )
        if match:
            return match.group(0), match.start(), match.end()
    return None


def _variants_for(message: str, code: str, written: str) -> list[str]:
    """Approved spellings worth adding for a market the reader named."""
    canonical, names = _catalogue().get(code, ("", ()))
    folded_written = _fold(written)

    # The reader already wrote the market's configured name, so the spelling
    # the rest of the system uses is in the query and there is nothing to add.
    #
    # This is also what stops the alias dump. Without it, "France" collected
    # "Francë" - Albanian, an approved name for FR, folding to "france", and
    # certainly not the spelling in a Forever Living document. Every market
    # whose configured name is unaccented has neighbours like that in CLDR.
    # Réunion is the case that survives the rule, because its configured name
    # is "Reunion Islands" and the reader who writes "Reunion" has not used it.
    if canonical and _fold(canonical) == folded_written:
        return []

    # Sorted for determinism, not preference. A market can have more than one
    # accented spelling - Réunion is written "Réunion" in French and "Reunión"
    # in Spanish - and the generated catalogue keeps only a flat set of names,
    # discarding which language produced each one. So there is no local basis
    # for ranking them by the market's own languages, and both are added rather
    # than one being picked on a guess. Retaining the language in
    # scripts/generate-market-name-aliases.mjs would remove the ambiguity; that
    # is a change to generated data and is not made here.
    accent_variants = sorted(
        {
            name
            for name in names
            if _fold(name) == folded_written and name.casefold() != written.casefold()
        }
    )

    chosen: list[str] = []
    for name in accent_variants:
        if name not in chosen:
            chosen.append(name)

    # The configured name, when the reader used something else for the same
    # market - an abbreviation, a shorter form, or another language's name.
    if canonical and _fold(canonical) != folded_written and canonical not in chosen:
        chosen.append(canonical)

    # A spelling the question already contains adds no term the search could
    # not already reach. Compared case-insensitively but NOT folded: an
    # accented variant folds to what the reader wrote by definition, so folding
    # here would discard the one variant this exists to add.
    return [
        name
        for name in chosen
        if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", message or "", flags=re.IGNORECASE)
    ][:_MAX_VARIANTS_PER_MARKET]


def country_name_queries(message: str) -> list[str]:
    """Extra search phrases carrying approved spellings of the named markets.

    Each is the reader's own question with one country name swapped for another
    approved spelling of the same market, so the topic of the question survives
    into the added query. A bare country name would rank the market's documents
    and lose what was being asked about them.
    """
    if not settings.OPENSEARCH_COUNTRY_NAME_EXPANSION_ENABLED:
        return []
    if not message or not message.strip():
        return []

    # Ordered by where each market appears in the question, not by country
    # code. Sorting by code spent the whole budget on Belgium and the DRC in
    # "Compare Reunion, DRC, Belgium, France and Guinea" and never reached
    # Réunion, which was the market that needed the spelling.
    spans: list[tuple[int, str, str, int, int]] = []
    for code in find_market_mentions(message):
        span = _written_span(message, code)
        if span is not None:
            written, start, end = span
            spans.append((start, code, written, start, end))

    queries: list[str] = []
    for _, code, written, start, end in sorted(spans)[:_MAX_MARKETS]:
        for variant in _variants_for(message, code, written):
            expanded = f"{message[:start]}{variant}{message[end:]}"
            if expanded != message and expanded not in queries:
                queries.append(expanded)
            if len(queries) >= _MAX_QUERIES:
                return queries
    return queries
