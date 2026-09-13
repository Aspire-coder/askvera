"""Demo W15: strip the longer configured market name before a shorter alias

inside it, so a follow-up naming a new market never strands a fragment of the
old one.

Defect (offline all-markets probe; see .../scratchpad/demo/all-markets-probe/
results.md sections 1a and 1c): ``_without_market_names`` tried candidate word
spans shortest-first. When a market's short standalone alias is itself a
substring of that market's longer configured name ("Reunion" inside "Reunion
Islands", "Congo" inside "Republic of Congo"), the short alias was accepted
and removed first, and the loop's own-word ``removed`` guard then blocked the
longer span from ever being tried - stranding the rest of the name:

    "What is the delivery cost in Cote d'Ivoire (Ivory Coast)?" + "And for
    Kenya?" -> "What is the delivery cost in Cote d'Ivoire ()? And for Kenya?"
    "What is the delivery cost in Reunion Islands?" + "And for Kenya?" ->
    "What is the delivery cost Islands? And for Kenya?"

Fix: candidate spans are now tried longest-first (by word count, then
leftmost), so a fully configured name is removed as one span before any
alias contained inside it is even considered, and a shorter span already
covered by a removed longer one is never separately removed. Confirming a
candidate span also now requires the span's own normalized text to exactly
equal a configured name (not merely contain one, the way ``find_market_
mentions`` checks a whole message) - otherwise the longest-first search can
mistake an accidental neighbour word for part of the name (an ambiguous
localized token, e.g. "a" from "Bosna a Hercegovina", sitting next to an
unrelated "turkey").

Every test here is offline: sockets, AWS clients, embeddings, the OpenSearch
client, the selector model and session/cache writes are stubbed to raise if
used.
"""

from __future__ import annotations

import socket

import pytest

import services.aws_clients as aws_clients
import services.embeddings as embeddings
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from services.market_config import (
    _normalize_market_text,
    find_market_mentions,
    load_global_directory_markets,
    load_market_config,
)


def _live_call(*_: object, **__: object):
    raise AssertionError("W15 tests must never make an AWS, embedding, OpenSearch, network or model call")


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _live_call)
    monkeypatch.setattr(socket, "create_connection", _live_call)
    monkeypatch.setattr(aws_clients, "get_aws_clients", _live_call)
    monkeypatch.setattr(embeddings, "embed_text", _live_call)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "embed_text", _live_call)
    monkeypatch.setattr(opensearch_sections, "_client", _live_call)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", _live_call)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", _live_call)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", _live_call)


def _replace(anchor: str, message: str) -> str:
    return AIOrchestrator()._replace_directory_target(anchor, message)


def _targets(anchor: str, message: str) -> set[str]:
    return opensearch_sections._directory_target_country_names(f"{_replace(anchor, message)} {message}", "US")


# --- Explicit cases from the defect report ------------------------------------------------

EXPLICIT_CASES = [
    (
        "What is the delivery cost in Cote d'Ivoire (Ivory Coast)?",
        "And for Kenya?",
        "What is the delivery cost?",
    ),
    (
        "What is the delivery cost in Reunion Islands?",
        "And for Kenya?",
        "What is the delivery cost?",
    ),
    (
        "What is the delivery cost in Republic of Congo?",
        "And for Kenya?",
        "What is the delivery cost?",
    ),
    (
        "What is the delivery cost in Tanzania, United Republic of?",
        "And for Kenya?",
        "What is the delivery cost?",
    ),
    (
        "What is the delivery cost in Federated States of Micronesia?",
        "And for Kenya?",
        "What is the delivery cost?",
    ),
    (
        # Kenya-related name in the anchor, so the follow-up targets Uganda instead.
        "What is the delivery cost in El Salvador?",
        "And for Uganda?",
        "What is the delivery cost?",
    ),
]


@pytest.mark.parametrize("anchor,message,expected", EXPLICIT_CASES)
def test_longer_configured_name_is_removed_whole(anchor, message, expected) -> None:
    assert _replace(anchor, message) == expected
    assert "()" not in _replace(anchor, message)
    assert _replace(anchor, message).count("(") == _replace(anchor, message).count(")")


@pytest.mark.parametrize("anchor,message,expected", EXPLICIT_CASES)
def test_longer_configured_name_directory_target_is_the_new_market_only(anchor, message, expected) -> None:
    new_market = "Uganda" if message == "And for Uganda?" else "Kenya"
    assert _targets(anchor, message) == {new_market}


# --- Regression: earlier rules from W7/W8/W8b are unchanged -------------------------------


def test_same_market_anchor_with_a_contained_alias_is_still_untouched() -> None:
    # Kenya's own configured name is not disturbed by a Kenya follow-up (same market).
    anchor = "What is the delivery cost in Kenya?"
    assert _replace(anchor, "And for Kenya?") == anchor


def test_compound_market_reference_still_removed_whole_next_to_a_longer_name() -> None:
    anchor = "What are the office hours in Kenya/East Africa?"
    assert _replace(anchor, "What about Reunion Islands?") == "What are the office hours?"


# --- All configured markets and aliases ----------------------------------------------------
#
# For every unambiguous, enabled market name/alias in markets.json,
# global_directory_markets.json and the localized alias table, a follow-up
# naming a new market must leave no word of the old market's name behind and
# must never leave a stray/empty "()". Ambiguous aliases (an alias shared by
# more than one configured code, e.g. "Curazao" for both the historical
# Netherlands Antilles and the current Curacao market) are already excluded
# from stripping by ``find_market_mentions`` itself - unrelated to this fix,
# so they are skipped here the same way ``find_market_mentions`` would skip
# them when reading the anchor.
#
# A small set of aliases that contain the Turkish/Azerbaijani dotted capital I
# ("İ") are also skipped: casefolding "İ" produces a base "i" plus a combining
# dot-above mark that ``_normalize_market_text`` (shared with ``find_market_
# mentions``, unmodified by this fix) then treats as a word break, splitting
# one configured name into two normalized tokens the word span logic never
# rejoins. This reproduces identically on an unmodified checkout, is not the
# "short alias inside a longer name" defect this change fixes, and is out of
# the allowed edit scope (only ``_without_market_names`` and its direct
# span-selection helpers).
_KNOWN_UNRELATED_RESIDUAL_CHARACTER = "İ"  # LATIN CAPITAL LETTER I WITH DOT ABOVE


def _all_catalog_names() -> list[str]:
    catalog = [*load_market_config()["markets"], *load_global_directory_markets()]
    names = [str(market.get("name") or "") for market in catalog if market.get("enabled", True)]
    names.extend(
        name
        for aliases in chat_orchestrator._localized_market_names().values()
        for name in aliases
    )
    return [name for name in names if name.strip()]


def _unambiguous_catalog_names() -> list[tuple[str, frozenset[str]]]:
    cases = []
    for name in _all_catalog_names():
        if _KNOWN_UNRELATED_RESIDUAL_CHARACTER in name:
            continue
        codes = find_market_mentions(name)
        if not codes:
            continue
        cases.append((name, frozenset(codes)))
    return cases


ALL_MARKET_CASES = _unambiguous_catalog_names()
KENYA_CODES = frozenset(find_market_mentions("Kenya"))
STOPWORDS = {"and", "of", "the"}


@pytest.mark.parametrize("name,codes", ALL_MARKET_CASES, ids=[case[0] for case in ALL_MARKET_CASES])
def test_every_configured_market_name_is_fully_stripped_for_a_new_market_follow_up(name, codes) -> None:
    new_market = "Uganda" if codes == KENYA_CODES else "Kenya"
    anchor = f"What is the delivery cost in {name}?"
    message = f"And for {new_market}?"
    result = _replace(anchor, message)
    full = f"{result} {message}".strip()

    assert "()" not in full
    assert full.count("(") == full.count(")")

    old_words = set(_normalize_market_text(name).split())
    new_words = set(_normalize_market_text(new_market).split())
    leftover_words = set(_normalize_market_text(result).split())
    stray = (old_words - new_words - STOPWORDS) & leftover_words
    assert not stray, f"{name!r} left {stray!r} behind in {result!r}"

    assert opensearch_sections._directory_target_country_names(full, "US") == {new_market}


def test_all_market_case_coverage_is_substantial() -> None:
    # Sanity check that the parametrization above actually exercises the
    # catalog and was not accidentally emptied by the skip filters.
    assert len(ALL_MARKET_CASES) > 3000
