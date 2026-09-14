"""International Sponsoring Directory country-name resolution.

Covers the alias-routing (category A) and overlap-resolution (category B)
cases from the QA test plan's 161-case set that previously resolved to a
generic, ISO-code-based country name instead of the sponsoring directory's
own section label (e.g. "UK" -> "United Kingdom" instead of "England").
Question text and expected section names are copied verbatim from the
test-plan cases so this file stays traceable to that source.

Every case asserts on ``_directory_target_section_names`` - the function that
layers the sponsoring-directory alias table
(config/sponsoring_directory_country_aliases.json) on top of the untouched
``_directory_target_country_names``, and is the one this app's real
directory search actually calls. ``_directory_target_country_names`` itself
is deliberately left alone by this fix and is not exercised here except as
a baseline in a couple of comments.

Two review rounds found and fixed real bugs in the layering itself, both
now covered by dedicated tests below: round 2 found an alias match
unconditionally discarding a second, non-aliased country named in the same
message; round 3 found a looser fix for that reintroducing the same class
of data loss through short alias terms ("China", "American", "Netherlands",
...) that happened to be substrings of an unrelated market's longer name.
"""

from __future__ import annotations

import pytest

from app.retrieval.opensearch_sections import _directory_target_section_names
from services import market_config
from services.market_config import find_sponsoring_directory_alias_countries

# Selected_country is irrelevant to every case below: each question names its
# own country, and the sponsoring alias table takes priority over the
# session's own market. "US" mirrors the QA audit script's convention.
_SELECTED_COUNTRY = "US"

# Category A + B cases that resolved to the wrong (or no) sponsoring
# directory section before this fix, copied verbatim (id, question,
# expected_section) from test_cases_161.json.
PREVIOUSLY_FAILING_CASES: list[tuple[str, str, str]] = [
    ("T001", "What's the phone number for the UK office?", "England"),
    ("T002", "I'm in the United Kingdom, how do I order?", "England"),
    ("T003", "I live in Wales - which office serves me?", "England"),
    ("T004", "I'm in Scotland, where do I order from?", "Scotland"),
    ("T005", "Northern Ireland delivery time?", "Ireland"),
    ("T007", "How do I sign up in the US?", "North America"),
    ("T008", "I'm in the USA - what's the minimum order to become an FBO?", "North America"),
    ("T009", "Canada minimum order?", "North America"),
    ("T010", "I'm Canadian, are there trainings near me?", "North America"),
    ("T015", "Who serves Eswatini?", "South Africa"),
    ("T016", "I'm in Swaziland - where do I order?", "South Africa"),
    ("T017", "Dubai product centre opening hours?", "United Arab Emirates"),
    ("T018", "I'm in Saudi Arabia, where can I pick up products?", "United Arab Emirates"),
    ("T019", "Kuwait - which office handles me?", "United Arab Emirates"),
    ("T020", "Macau ordering options?", "Hong Kong"),
    ("T023", "Latvia - which office?", "Baltics"),
    ("T024", "Who covers Andorra?", "Spain"),
    ("T025", "Gibraltar delivery time?", "Spain"),
    ("T026", "Which office covers the Republic of Congo?", "Democratic Rep. of Congo"),
    ("T027", "DRC office address?", "Democratic Rep. of Congo"),
    ("T028", "I'm in Turkiye, what's the office number?", "Turkey"),
    ("T030", "Reunion - which section applies?", "Réunion Island"),
    ("T031", "I'm in Guinea Conakry, who serves me?", "Guinea Bissau and Guinea Conakry"),
    ("T036", "Who covers Mauritania?", "Senegal"),
    ("T037", "Zimbabwe - where do I order?", "South Africa"),
    ("T038", "Botswana product centres?", "South Africa"),
    ("T039", "Lebanon - which office?", "United Arab Emirates"),
    ("T040", "Palestine signing up?", "United Arab Emirates"),
    ("T041", "Martinique - how do I place orders?", "St. Maarten"),
    ("T042", "St Barthelemy office phone?", "St Marteen & St Barthelemy"),
    ("T045", "East Africa office number?", "Kenya/East Africa"),
    ("T063", "I'm in Guinea Bissau - what's the minimum order to become an FBO?", "Guinea Bissau and Guinea Conakry"),
    ("T064", "I'm in Guinea Conakry - what's the minimum order to become an FBO?", "Guinea Bissau and Guinea Conakry"),
    ("T081", "I'm in Réunion - what's the minimum order to become an FBO?", "Réunion Island"),
]

# A sample of cases that already resolved correctly before this fix -
# regression protection, spread across both categories.
ALREADY_PASSING_CASES: list[tuple[str, str, str]] = [
    ("T006", "I'm in the Republic of Ireland, what's the minimum first order?", "Ireland"),
    ("T011", "What's the minimum order in Mexico?", "Mexico"),
    ("T012", "Holland office hours please", "Netherlands Benelux"),
    ("T013", "Which office covers the Netherlands?", "Netherlands Benelux"),
    ("T014", "Côte d'Ivoire phone number?", "Ivory Coast"),
    ("T021", "How do I sign up in Czechia?", "Czech Republic"),
    ("T022", "South Korea bonus payment?", "Korea"),
    ("T029", "Slovakia signing up?", "Slovak Republic"),
    ("T032", "Luxembourg minimum order?", "Luxemburg"),
    ("T033", "I'm in Mainland China, how do I order?", "China"),
    ("T043", "New Zealand minimum order?", "New Zealand"),
    ("T044", "I'm in Brasil - payment methods?", "Brazil"),
    ("T046", "I'm in Algeria - what's the minimum order to become an FBO?", "Algeria"),
    ("T083", "I'm in Singapore - what's the minimum order to become an FBO?", "Singapore"),
]

# T130 (category E, anti-hallucination): a currency mention ("US dollars")
# must never steal the message from a named country. Tracked separately
# from PREVIOUSLY_FAILING_CASES because it is the fix for review round 2's
# blocking bug 1 (the "US"/"us" pronoun collision), not part of the
# original 89/89 alias-routing/overlap-resolution set.
ANTI_HALLUCINATION_REGRESSION_CASE = ("T130", "Convert the Poland delivery cost to US dollars", "Poland")

# Tightened per review: every case above must resolve to EXACTLY the
# expected section - no extra name alongside it (e.g. "United Kingdom"
# surviving next to "England"), which a looser `in` check would have missed.
ALL_SINGLE_COUNTRY_CASES = [*PREVIOUSLY_FAILING_CASES, *ALREADY_PASSING_CASES, ANTI_HALLUCINATION_REGRESSION_CASE]


@pytest.mark.parametrize("case_id,question,expected_section", ALL_SINGLE_COUNTRY_CASES, ids=[c[0] for c in ALL_SINGLE_COUNTRY_CASES])
def test_single_country_case_resolves_to_exactly_the_expected_section(case_id: str, question: str, expected_section: str) -> None:
    resolved = _directory_target_section_names(question, _SELECTED_COUNTRY)
    assert resolved == {expected_section}, f"{case_id}: resolved={sorted(resolved)!r} expected {{{expected_section!r}}}"


def test_st_maarten_and_st_barthelemy_are_distinct_sections() -> None:
    """St. Maarten and St Marteen & St Barthelemy are two different sections for
    two different sets of alias terms - Martinique/Sint Maarten/Saint Martin/
    St Martin route to "St. Maarten"; St Barth/St Barthelemy/Saint Barthelemy
    route to "St Marteen & St Barthelemy". They must never be merged.
    """
    st_maarten = _directory_target_section_names("Martinique - how do I place orders?", _SELECTED_COUNTRY)
    assert st_maarten == {"St. Maarten"}

    st_barthelemy = _directory_target_section_names("St Barthelemy office phone?", _SELECTED_COUNTRY)
    assert st_barthelemy == {"St Marteen & St Barthelemy"}


def test_sponsoring_alias_table_takes_priority_over_generic_country_name() -> None:
    """The generic market-code resolution alone would map "UK" to markets.json's
    "United Kingdom"; the sponsoring directory's own section is "England".
    """
    resolved = _directory_target_section_names("What's the phone number for the UK office?", _SELECTED_COUNTRY)
    assert resolved == {"England"}
    assert "United Kingdom" not in resolved


# --- Review round 2, blocking bug 1: short bare alias terms colliding with ---
# --- ordinary words ("us"/"ni"/"roi") ----------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Send us the Poland office address", {"Poland"}),
        ("What does it cost us to order in Italy?", {"Italy"}),
    ],
)
def test_bare_us_pronoun_is_never_treated_as_a_north_america_mention(message: str, expected: set[str]) -> None:
    """"us" as an ordinary object pronoun (not preceded by "in"/"the") must
    never be read as the country code "US" - it previously stole the
    message from whatever country actually was named. Tightened to the
    exact expected set per review round 3 (a looser `not in` check would
    have missed a co-mention data-loss regression on the *other* country).
    """
    resolved = _directory_target_section_names(message, _SELECTED_COUNTRY)
    assert resolved == expected


def test_us_dollars_currency_mention_does_not_override_the_named_country() -> None:
    """T130: "US" immediately followed by "dollars" (a currency, not a
    country reference) must not resolve to North America - and must not
    hide the country the message actually named.
    """
    case_id, question, expected_section = ANTI_HALLUCINATION_REGRESSION_CASE
    resolved = _directory_target_section_names(question, _SELECTED_COUNTRY)
    assert resolved == {expected_section}, case_id


def test_bare_us_still_resolves_when_it_is_actually_a_location() -> None:
    """Contrast case: "in the US" is a real, if terse, location reference and
    must still resolve - this is T007, load-bearing for the whole guard
    design (it rules out simply dropping the bare "US" alias term)."""
    resolved = _directory_target_section_names("How do I sign up in the US?", _SELECTED_COUNTRY)
    assert resolved == {"North America"}


def test_short_alias_term_checks_every_occurrence_not_just_the_first() -> None:
    """"Send us the address; I am in the US" has a non-locative "us" first
    and a locative "US" second - the second, genuine occurrence must still
    be found (review round 3 non-blocking item 1: the guard used to check
    only the first occurrence via ``str.find``).
    """
    resolved = _directory_target_section_names("Send us the address; I am in the US", _SELECTED_COUNTRY)
    assert resolved == {"North America"}


def test_spanish_ni_and_french_roi_never_resolve_to_ireland() -> None:
    """Spanish "ni" ("nor") and French "roi" ("king") are ordinary words in
    those languages, not country codes - bare "NI"/"RoI" were dropped from
    the alias table entirely (no test case needs them; only the spelled-out
    "Northern Ireland"/"Republic of Ireland"/"Eire" forms are used anywhere
    in the 161-case test plan). Tightened to exact sets per review round 3.
    """
    assert _directory_target_section_names("Nos gustaria que nos digas ni el horario", _SELECTED_COUNTRY) == set()
    resolved = _directory_target_section_names("Le roi de France est parti", _SELECTED_COUNTRY)
    assert resolved == {"France"}


# --- Review round 2, blocking bug 2: naming two countries in one message ----
# --- must not lose one of them -----------------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Compare Uganda and Dubai delivery times", {"Uganda", "United Arab Emirates"}),
        ("Ghana office and Saudi office", {"Ghana", "United Arab Emirates"}),
        ("Is the minimum order the same in Uganda and the UK?", {"Uganda", "England"}),
    ],
)
def test_co_mentioning_an_aliased_and_a_plain_country_keeps_both(message: str, expected: set[str]) -> None:
    """The alias table must substitute only the specific country/countries it
    actually matched (its generic name swapped for the directory's section
    name); a country it has no opinion about, mentioned in the same
    message, must survive untouched - and must not appear twice under two
    different names (e.g. "United Kingdom" surviving alongside "England").
    """
    resolved = _directory_target_section_names(message, _SELECTED_COUNTRY)
    assert resolved == expected


# --- Review round 3, blocking bug: a looser containment check in the -------
# --- supersede logic reintroduced co-mention data loss through a different --
# --- path - a matched alias term's SHORT/ordinary name/word turned out to ---
# --- be a substring of an unrelated, longer market name or alias -----------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("China and Hong Kong offices", {"China", "Hong Kong"}),
        ("East Africa and Kenya offices", {"Kenya/East Africa", "Kenya"}),
        ("Compare Reunion Island and Iceland delivery", {"Réunion Island", "Iceland"}),
        ("American Samoa and the US", {"American Samoa", "North America"}),
        ("Netherlands Antilles and Holland", {"Netherlands Antilles", "Netherlands Benelux"}),
        ("Guinea Bissau and Guinea offices", {"Guinea Bissau and Guinea Conakry", "Guinea"}),
    ],
)
def test_short_alias_term_never_supersedes_an_unrelated_code_it_merely_sits_inside(
    message: str, expected: set[str]
) -> None:
    """A matched alias term ("China", "American", "Netherlands", ...) must
    only supersede a market code's generic name when that exact term is
    itself unambiguously recognized by ``find_market_mentions`` as naming
    that code - never merely because it is a short substring of some
    unrelated market's longer name or localized alias ("china" inside
    "Hong Kong SAR China", "american" inside "American Samoa",
    "netherlands" inside "Netherlands Antilles", "island"/"guinea"/"kenya"
    inside a longer alias-table term itself). Each pair here previously lost
    its second, unrelated country to exactly this mistake.
    """
    resolved = _directory_target_section_names(message, _SELECTED_COUNTRY)
    assert resolved == expected


# --- Kenya/Guinea carve-out: owner decision, pinned so it is never lost -----
# --- track of silently -------------------------------------------------------


def test_bare_kenya_and_guinea_carve_out_is_pinned() -> None:
    """Bare "Kenya" and bare "Guinea" are deliberately NOT in the sponsoring
    alias table, even though the reference system prompt's alias list
    includes them (Kenya/East Africa <- ... Kenya; Guinea Bissau and Guinea
    Conakry <- Guinea, ...). Two pre-existing tests
    (test_demo_longest_alias_stripping.py's 3000+ follow-up-target cases and
    test_demo_followup_target_replacement.py) require these bare words to
    resolve to their own generic market name, not the grouped directory
    section - and the user was asked directly and chose to keep that
    behavior rather than change it (2026-09-14).

    This is a disclosed, accepted gap: test_cases_161.json's T093, T104,
    T134 ("...in Kenya?" wording) and T159 ("...in Guinea?" wording) expect
    the grouped section name and currently do NOT get it - see the
    audit_alias_routing_full.py run in the handoff. This test pins today's
    actual (carved-out) behavior for one of each so a future change to the
    alias table notices this decision instead of silently drifting.
    """
    kenya = _directory_target_section_names("Minimum purchase to register as a distributor in Kenya?", _SELECTED_COUNTRY)
    assert kenya == {"Kenya"}  # NOT {"Kenya/East Africa"} - see docstring

    guinea = _directory_target_section_names("Minimum order in Guinea?", _SELECTED_COUNTRY)
    assert guinea == {"Guinea"}  # NOT {"Guinea Bissau and Guinea Conakry"} - see docstring


# --- Supporting-function tests -----------------------------------------------


def test_short_alias_term_does_not_match_inside_unrelated_longer_market_name(monkeypatch) -> None:
    """A real alias term ("Guinea Bissau") must not fire when it is only a
    substring of a longer, unrelated configured market name ("Fooland
    Guinea Bissau") - the longer name must be consumed whole first, exactly
    as ``find_market_mentions`` already does for market discovery.
    """
    fake_markets = [*market_config.load_global_directory_markets(), {"name": "Fooland Guinea Bissau", "code": "ZZ"}]
    monkeypatch.setattr(market_config, "load_global_directory_markets", lambda: fake_markets)
    resolved = find_sponsoring_directory_alias_countries("What's the minimum order in Fooland Guinea Bissau?")
    assert resolved == set()


def test_no_alias_match_returns_empty_set() -> None:
    assert find_sponsoring_directory_alias_countries("What are your business hours today?") == set()
