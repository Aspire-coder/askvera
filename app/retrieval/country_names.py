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

1. A spelling that differs **only by diacritics** from an approved name inside
   what the reader wrote. Anchoring on a name *inside* the phrase rather than
   on the whole phrase is what makes this reach the wording that actually
   failed: "Reunion Island" contains "Reunion", whose accented sibling is
   "Réunion", and the phrase becomes "Réunion Island". Anchored on the whole
   phrase it found nothing, because no approved name folds to `reunion island`
   except that phrase itself.
2. The market's **configured canonical name**, which is the name the rest of
   the system already uses for that market. This is what carries `DRC` to
   `Democratic Republic of Congo`.

Neither applies when the reader typed the configured name exactly. That guard
is what stops the alias dump - without it "France" collects the Albanian
"Francë" - and it costs the case where the configured name is unaccented and
the record is not, which is "Reunion Islands" here. "Reunion Island" and
"Reunion" are unaffected, and those are the wordings readers use.

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


def _substitutions(
    message: str, code: str, written: str, start: int, end: int
) -> list[tuple[str, int, int]]:
    """Replacements to make in the message: (text, span start, span end).

    The accent match is anchored on **any approved name inside what the reader
    wrote**, not only on the whole phrase. That is the difference between
    working and not working on the question that actually failed: a reader who
    types "Reunion Island" has written an approved name whose accented siblings
    do not exist under that exact phrase - "Réunion" folds to `reunion`, not to
    `reunion island` - so anchoring on the whole phrase found nothing and the
    original failing wording gained no accented query at all. Anchoring on the
    "Reunion" inside it yields "Réunion Island", which is what the record says.

    The canonical name still replaces the whole phrase, since that is a
    different name rather than a respelling of part of one.
    """
    canonical, names = _catalogue().get(code, ("", ()))
    if canonical and _fold(canonical) == _fold(written):
        # The reader wrote the market's configured name, so the spelling the
        # rest of the system uses is already in the query.
        #
        # This is also what stops the alias dump. Without it "France" collects
        # "Francë" - Albanian, an approved name for FR, and certainly not the
        # spelling in a Forever Living document. Every market whose configured
        # name is unaccented has neighbours like that in CLDR.
        #
        # The cost is real and worth stating: a reader who types the configured
        # name exactly gets no expansion, even where the record spells it with
        # accents. "Reunion Islands" is that case. "Reunion Island" and
        # "Reunion" are not, and those are the wordings readers use.
        return []

    substitutions: list[tuple[str, int, int]] = []
    seen: set[str] = set()

    # Anchors: approved names occurring inside the written phrase, longest
    # first, so "Equatorial Guinea" is respelled as itself and never through
    # the "Guinea" inside it.
    for anchor in sorted(names, key=len, reverse=True):
        anchor_match = re.search(
            rf"(?<!\w){re.escape(anchor)}(?!\w)", written, flags=re.IGNORECASE
        )
        if not anchor_match:
            continue
        for variant in _accent_variants(names, anchor_match.group(0)):
            if variant.casefold() in seen or _appears_in(message, variant):
                continue
            seen.add(variant.casefold())
            substitutions.append(
                (variant, start + anchor_match.start(), start + anchor_match.end())
            )
        if substitutions:
            break

    if canonical and not _appears_in(message, canonical) and canonical.casefold() not in seen:
        substitutions.append((canonical, start, end))

    return substitutions[:_MAX_VARIANTS_PER_MARKET]


def _appears_in(message: str, name: str) -> bool:
    """Whether the message already uses this exact spelling.

    Case-insensitive but NOT accent-folded: an accented variant folds to what
    the reader wrote by definition, so folding here would discard the one
    variant this exists to add.
    """
    return bool(
        re.search(rf"(?<!\w){re.escape(name)}(?!\w)", message or "", flags=re.IGNORECASE)
    )


def _accent_variants(names: tuple[str, ...], anchor: str) -> list[str]:
    """Approved spellings of `anchor` differing from it only by diacritics."""
    folded = _fold(anchor)
    # Sorted for determinism, not preference. A market can have more than one
    # accented spelling - Réunion is written "Réunion" in French and "Reunión"
    # in Spanish - and the generated catalogue keeps only a flat set of names,
    # discarding which language produced each. So there is no local basis for
    # ranking them by the market's own languages, and both are added rather
    # than one being picked on a guess. Retaining the language in
    # scripts/generate-market-name-aliases.mjs would remove the ambiguity; that
    # is a change to generated data and is not made here.
    return sorted(
        {
            name
            for name in names
            if _fold(name) == folded and name.casefold() != anchor.casefold()
        }
    )


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

    # An expanded query must name the same markets as the question did.
    #
    # Substituting inside a phrase can change what the phrase resolves to.
    # "Reunion Island" is a configured name and matches whole; "Réunion Island"
    # is not, so the matcher takes "Réunion" and then reads the leftover
    # "Island" as Iceland, which is its name in German and Danish. The query
    # would have carried an unrelated market into ranking - the exact thing the
    # negative controls exist to prevent, arriving from the fix rather than
    # from the catalogue.
    #
    # Access is unaffected either way: locale searches filter on the session's
    # country and directory targeting reads the original message. This is about
    # what the query text can rank, which is reason enough.
    intended_markets = find_market_mentions(message)

    queries: list[str] = []
    for _, code, written, start, end in sorted(spans)[:_MAX_MARKETS]:
        for variant, span_start, span_end in _substitutions(
            message, code, written, start, end
        ):
            expanded = f"{message[:span_start]}{variant}{message[span_end:]}"
            if find_market_mentions(expanded) != intended_markets:
                continue
            if expanded != message and expanded not in queries:
                queries.append(expanded)
            if len(queries) >= _MAX_QUERIES:
                return queries
    return queries
